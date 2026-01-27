import math
from abc import ABC, abstractmethod
from typing import ClassVar

import polars as pl
import time_stream as ts
from time_stream.operation import Operation

from dritimeseriesprocessor.models.domain_models.processing_config import ProcessingMethodConfig
from dritimeseriesprocessor.utils.enums import OperationType
from dritimeseriesprocessor.utils.time_stream_utils import merge_multiple_timeframes


class DerivationMethod(Operation, ABC):
    operation_type: OperationType.DERIVATION
    inputs: ClassVar[tuple]

    def run(self, config: ProcessingMethodConfig) -> ts.TimeFrame:
        """Execute the common workflow to carry out a derivation calculation.

        Args:
            config: Configuration parameters including input TimeFrames and output specs

        Returns:
            TimeFrame containing the calculated derived variable
        """
        # Extract and merge input data
        tf_map = {name: config.params[name] for name in self.inputs}
        merged_tf = merge_multiple_timeframes(list(tf_map.values()))

        # Get column references for calculation
        columns = {name: pl.col(tf.metadata["column_name"]) for name, tf in tf_map.items()}

        # Perform the calculation (subclass-specific)
        calculation_expr = self.expr(columns).alias(config.params["output_col"])
        result_df = merged_tf.df.with_columns(calculation_expr)
        print(result_df)

        # Apply any rounding if required
        if config.argument.get("round", None) is not None:
            result_df = result_df.with_columns(
                pl.col(config.params["output_col"]).round(config.argument["round"]).alias(config.params["output_col"])
            )

        # Build output TimeFrame
        return (
            ts.TimeFrame(
                df=result_df,
                time_name=merged_tf.time_name,
                resolution=config.params["resolution"],
                periodicity=config.params["periodicity"],
            )
            .with_metadata({"column_name": config.params["output_col"]})
            .select(config.params["output_col"])
        )

    @abstractmethod
    def expr(self, columns: dict[str, pl.Expr]) -> pl.Expr:
        """Define the calculation expression for this derivation.

        Args:
            columns: Dictionary mapping variable names to Polars column expressions

        Returns:
            Polars expression that computes the derived variable
        """
        pass


@DerivationMethod.register
class NetRadiation(DerivationMethod):
    """Calculate net radiation

    Expects MethodConfig.params to contain:
    {
        "swin": <TimeFrame> Incoming shortwave radiation [W m-2]
        "swout": <TimeFrame> Outgoing shortwave radiation [W m-2]
        "lwin": <TimeFrame> Incoming longwave radiation [W m-2]
        "lwout": <TimeFrame> Outgoing longwave radiation [W m-2]
        "output_col": <str> Required name of output
        "resolution": <str> Expected output resolution
        "periodicity": <str> Expected output periodicity
    }
    """

    name = "calculate_rn"
    inputs = ("swin", "swout", "lwin", "lwout")

    def expr(self, columns: dict[str, pl.Expr]) -> pl.Expr:
        """Calculate net radiation (rn) [W m-2]

        Args:
            columns: Dict with keys of required columns for the calculation.

        Returns:
            Polars expression computing rn
        """
        return columns["swin"] - columns["swout"] + columns["lwin"] - columns["lwout"]


@DerivationMethod.register
class MeanG(DerivationMethod):
    """Calculate the mean soil heat flux (g) from inputs from multiple soil heat flux measurements."""

    name = "calc_mean_g"
    inputs = ("g1", "g2")

    def expr(self, columns: dict[str, pl.Expr]) -> pl.Expr:
        """Calculate mean soil heat flux (g) [MJ m-2 30min-1]

        Args:
            columns: Dict with keys of required columns for the calculation.

        Returns:
            Polars expression computing g
        """
        g1 = columns["g1"]
        g2 = columns["g2"]

        return pl.mean_horizontal(g1, g2)


@DerivationMethod.register
class PET30Min(DerivationMethod):
    """Calculate Potential Evapotranspiration (PET) (30 min).

    Steps taken from Penman-Monteith Evapotranspiration (FAO-56 Method)
        https://www.fao.org/4/x0490e/x0490e06.htm#equation

        For hourly examples see eq53:
        https://www.fao.org/4/x0490e/x0490e08.htm

        "With the advent of electronic, automated weather stations, weather data are increasingly reported for
            hourly or shorter periods ... When applying the FAO Penman-Monteith equation on an hourly or shorter
            timescale, the equation and some of the procedures for calculating meteorological data should be
            adjusted for the smaller time step"

    Expects MethodConfig.params to contain:
    {
        "rn": <TimeFrame> Net radiation [MJ m-2 30min-1]
        "g": <TimeFrame> Soil heat flux density [MJ m-2 30min-1]
        "ta": <TimeFrame> Air temperature [degC]
        "rh": <TimeFrame> Relative humidity [%]
        "ws": <TimeFrame> Wind speed at 2m height [ms-1]
        "pa": <TimeFrame> Atmospheric pressure [hPa]
        "output_col": <str> Required name of output
        "resolution": <str> Expected output resolution
        "periodicity": <str> Expected output periodicity
    }
    """

    name = "calculate_pe"
    inputs = ("g", "pa", "rh", "rn", "ta", "ws")

    def expr(self, columns: dict[str, pl.Expr]) -> pl.Expr:
        """Calculate potential evapotranspiration (pet) [mm day-1]

        Args:
            columns: Dict with keys of required columns for the calculation.

        Returns:
            Polars expression computing pet
        """
        g = columns["g"]
        pa = columns["pa"]
        rh = columns["rh"]
        rn = columns["rn"]
        ta = columns["ta"]
        ws = columns["ws"]

        # TODO: get wind height from metadata
        wind_height = 2.6

        es = self.saturation_vapour_pressure(ta)
        ea = self.actual_vapour_pressure(es, rh)
        vpd = es - ea  # Vapour pressure deficit
        delta = self.vapour_pressure_curve_slope(es, ta)
        lv = self.latent_heat_of_vaporization(ta)
        gamma = self.psychrometric_constant(pa, lv)
        ws_2m = self.wind_speed_height_correction(ws, wind_height)

        # Convert RN and G from W/m2 - MJ per 30 min (if upstream provides W/m2)
        rn_mj = rn * 0.0018
        g_mj = g * 0.0018

        # FAO constants
        # Note: The Numerator and denominator constants for reference type and calculation time step are defined in the
        # following references:
        #     Allen, R. G., Walter, I. A., Elliot, R. L., Howell, T.A., Itenfisu, D., Jensen, M. E.
        #         and Snyder, R. 2005. The ASCE standardized reference evapotranspiration equation. ASCE and American
        #         Society of Civil Engineers.
        #
        #     FAO-56 Chapter 4 - Determination of ETo - "Hourly time step"
        #         https://www.fao.org/4/x0490e/x0490e08.htm

        # Numerator given as 900 for daily, and 37 for hourly. Here for 30 min data, adjusted to
        #   900 / 48 = 18.75 (rounded to 19)
        reference_crop_type_numerator = 19
        # Denominator is the same between daily and hourly in FAO-56 Chapter 4, eq. 53. Assume same is okay for 30min.
        reference_crop_type_denominator = 0.34

        # PET equation (FAO-56, adapted to 30-minute)
        radiation_term = 0.408 * delta * (rn_mj - g_mj)
        aerodynamic_term = gamma * (reference_crop_type_numerator / (ta + 273)) * ws_2m * vpd
        resistance_term = delta + gamma * (1 + (reference_crop_type_denominator * ws_2m))

        return (radiation_term + aerodynamic_term) / resistance_term

    @staticmethod
    def saturation_vapour_pressure(ta: pl.Expr) -> pl.Expr:
        """Saturation vapour pressure (es) [kPa]

        Steps taken from FAO-56 method (eq11) https://www.fao.org/4/x0490e/x0490e07.htm#calculation%20procedures

        Args:
            ta: Air temperature [degC]

        Returns:
            Polars expression to calculate es
        """
        return 0.6108 * ((17.27 * ta) / (ta + 237.3)).exp()

    @staticmethod
    def actual_vapour_pressure(es: pl.Expr, rh: pl.Expr) -> pl.Expr:
        """Actual vapour pressure (ea) [kPa]

        Steps taken from FAO-56 1-hour method (eq54) https://www.fao.org/4/x0490e/x0490e08.htm

        Args:
            es: Saturation vapour pressure [kPa]
            rh: Relative humidity [%]

        Returns:
            Polars expression to calculate ea
        """
        return es * (rh / 100)

    @staticmethod
    def vapour_pressure_curve_slope(es: pl.Expr, ta: pl.Expr) -> pl.Expr:
        """Slope of vapour pressure curve (delta) [kPa degC-1]

        Steps taken from FAO-56 method (eq13) https://www.fao.org/4/x0490e/x0490e07.htm#calculation%20procedures

        Args:
            es: Saturation vapour pressure [kPa]
            ta: Air temperature [degC]

        Returns:
            Polars expression to calculate delta
        """
        return (4098 * es) / ((ta + 237.3) ** 2)

    @staticmethod
    def latent_heat_of_vaporization(ta: pl.Expr) -> pl.Expr:
        """Latent heat of vaporization (lambda) [MJ kg-1]

        Steps taken from Harrison (1963), referenced by FAO Annex 3 https://www.fao.org/4/x0490e/x0490e0k.htm

        Harrison, L.P. 1963. "Fundamental concepts and definitions relating to humidity."
            In: Wexler, A. & Wildhack, W.A. (eds.) Humidity and Moisture. Vol. 3. Reinhold Publishing Company, New York

        Args:
            ta: Air temperature [degC]

        Returns:
            Polars expression to calculate lambda
        """
        return 2.501 - (2.361e-3 * ta)

    @staticmethod
    def psychrometric_constant(pa: pl.Expr, lv: pl.Expr) -> pl.Expr:
        """Psychrometric constant (gamma) [kPa degC-1]

        Steps taken from FAO-56 method (eq8) https://www.fao.org/4/x0490e/x0490e07.htm#psychrometric%20constant%20(g)

        Args:
            pa: Atmospheric pressure [hPa]
            lv: Latent heat of vaporization [MJ/kg]

        Returns:
            Polars expression to calculate gamma
        """
        cp = 1.013e-3  # Specific heat at constant pressure
        e_ratio = 0.622  # Ratio molecular weight of water vapour/dry air
        return (cp * (pa / 10)) / (e_ratio * lv)

    @staticmethod
    def wind_speed_height_correction(ws: pl.Expr, measured_height: float) -> pl.Expr:
        """Convert wind speed to 2m height [ms-1]

        Steps taken from FAO-56 method (eq47) https://www.fao.org/4/x0490e/x0490e07.htm#wind%20profile%20relationship

        Args:
            ws: Wind speed measured at given height [ms-1]
            measured_height: The height the wind was measured at [m]

        Returns:
            Polars expression to calculate gamma
        """
        return ws * (4.87 / math.log((67.8 * measured_height) - 5.42))


'''
@DerivationMethod.register
class WD(DerivationMethod):
    name = "calc_daily_wd"
    inputs = ("wd",)

    def expr(self, columns: dict[str, pl.Expr]) -> pl.Expr:
        """Calculate ...

        Args:
            columns: ...

        Returns:
            Polars expression ...
        """

        wd = columns["wd"]

        return wd

    @staticmethod
    def calc_daily_WD(wd: pl.Expr) -> pl.Expr:
        """Calculate average wind direction using Yamartino method. See: https://en.wikipedia.org/wiki/Yamartino_method

        Args:
            wd: wind direction, measured in degrees

        Returns:
            daily_wd: daily wind direction, measured in degrees

        """

        sin_sum = ((wd.radians()).sin()).sum()  # / len(wd)
        cos_sum = ((wd.radians()).cos()).sum()  # / len(wd)
        daily_wd = pl.arctan2(sin_sum, cos_sum).degrees()

        # No longer needed, taken care of by atan2
        # if sin_sum.gt(0) and cos_sum.gt(0):
        #    pass
        # elif cos_sum.lt(0):
        #    daily_wd += 180
        # else:
        #    daily_wd += 360

        return daily_wd
'''
