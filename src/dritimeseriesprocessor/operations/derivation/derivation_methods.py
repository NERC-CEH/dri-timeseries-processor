import math
from abc import ABC, abstractmethod
from typing import ClassVar

import polars as pl
import time_stream as ts
from time_stream.operation import Operation

from dritimeseriesprocessor.models.domain_models.processing_config import DataProcessingMethodConfig
from dritimeseriesprocessor.utils.enums import OperationType
from dritimeseriesprocessor.utils.polars_utils import join_time_intervals
from dritimeseriesprocessor.utils.time_stream_utils import merge_multiple_timeframes


class DerivationMethod(Operation, ABC):
    operation_type: OperationType.DERIVATION
    inputs: ClassVar[tuple]

    def run(self, config: DataProcessingMethodConfig) -> ts.TimeFrame:
        """Execute the common workflow to carry out a derivation calculation.

        Args:
            config: Configuration parameters including input TimeFrames and output specs

        Returns:
            TimeFrame containing the calculated derived variable
        """

        self.config = config

        # Extract and merge input data
        tf_map = {name: config.params[name] for name in self.inputs}
        merged_tf = merge_multiple_timeframes(list(tf_map.values()))

        # Get column references for calculation
        columns = {name: pl.col(tf.metadata["column_name"]) for name, tf in tf_map.items()}

        # Build data columns for any time-bound deployment attributes (e.g. anemometer sensor height)
        for param, value in config.params.items():
            if isinstance(value, dict) and value.get(f"{param}.source", "") == "deployment":
                # Join the deployment values to the main DataFrame
                merged_tf = merged_tf.with_df(
                    join_time_intervals(value[f"{param}.value"], merged_tf.df, merged_tf.time_name, param)
                )
                # Make sure the deployment value column is available to any calculation method that needs it
                columns[param] = pl.col(param)

        # Perform the calculation (subclass-specific)
        calculation_expr = self.expr(columns).alias(config.params["output_col"])
        result_df = merged_tf.df.with_columns(calculation_expr)

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
class MeanSoilHeatFlux(DerivationMethod):
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
class MeanSeaLevelPressure(DerivationMethod):
    """Calculate the mean sea level pressure (mslp) from inputs PA and TA."""

    name = "calculate_mslp"
    inputs = ("pa", "ta")

    def expr(self, columns: dict[str, pl.Expr]) -> pl.Expr:
        """Calculate mean sea level pressure (mslp) [hPa]
        See US Standard Atmosphere, eq. 33a:
        https://ntrs.nasa.gov/api/citations/19770009539/downloads/19770009539.pdf
        See also: https://www.fao.org/4/x0490e/x0490e07.htm
        Args:
            columns: Dict with keys of required columns for the calculation: pa and ta.
            -pa: Atmospheric Pressure [hPa]
            -ta: Air Temperature [Celsius]

        Returns:
            Polars expression computing mslp
        """
        altitude = self.config.params["altitude"]
        pa = columns["pa"]
        ta = columns["ta"]

        return pa * (1 - ((0.0065 * altitude) / (ta + (0.0065 * altitude) + 273.15))).pow(-5.257)


@DerivationMethod.register
class PotentialEvapotranspiration30Min(DerivationMethod):
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
        wind_height = columns["wind_height"]

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
    def wind_speed_height_correction(ws: pl.Expr, measured_height: pl.Expr) -> pl.Expr:
        """Convert wind speed to 2m height [ms-1]

        Steps taken from FAO-56 method (eq47) https://www.fao.org/4/x0490e/x0490e07.htm#wind%20profile%20relationship

        Args:
            ws: Wind speed measured at given height [ms-1]
            measured_height: The height the wind was measured at [m]

        Returns:
            Polars expression to calculate wind speed height correction
        """
        return ws * (4.87 / ((67.8 * measured_height) - 5.42).log())


@DerivationMethod.register
class AbsoluteHumidity(DerivationMethod):
    """Calculate absolute humidity ('Q') from relative humidity and air temperature.
    Required for water vapour correction to CRS counts.
    Saturation vapour pressure, Psat (when relative humidity is 100%), is given by eq. 10 in Bolton's paper:
    https://doi.org/10.1175/1520-0493(1980)108%3C1046:TCOEPT%3E2.0.CO;2
    Relative humidity 100%:
    Psat = 6.11 exp((17.67 T)/(T + 243.5))
    Relative humidity of any value:
    Psat = 6.11 exp((17.67 T)/(T + 243.5))*rh/100
    Ideal gas formula: PV = nRT, => n = PV/(RT)
    molecular weight of water = 18.02 grams/mol
    Q = 18.02 * n
    => Q = 6.11 exp((17.67 T)/(T + 243.5))*rh*18.02/(100*R*(ta + 273.15))
         = 6.11 exp((17.67 T)/(T + 243.5))*rh*2.1674/(ta + 273.15)
    Q units: gram m^-3
    """

    name = "calculate_q"
    inputs = ("ta", "rh")

    def expr(self, columns: dict[str, pl.Expr]) -> pl.Expr:
        """Calculate absolute humidity Q [g m-3] (grams per cubic meter)
        Args:
            columns: Dict with keys of required columns for the calculation.
            - "ta": air temperature measured in Celsius.
            - "rh": relative humidity, measured as a percentage.
        Returns:
            Polars expression computing absolute humidity, Q
        """
        ta = columns["ta"]
        rh = columns["rh"]

        Q1 = ((17.67 * ta) / (ta + 243.5)).exp()
        Q2 = 273.15 + ta

        return (6.112 * Q1 * rh * 2.1674) / Q2


@DerivationMethod.register
class Albedo(DerivationMethod):
    """
    Calculate albedo from incoming and outgoing short wave radiation.
    Calculation uses latitude site attribute.
    See reference: https://www.fao.org/4/x0490e/x0490e07.htm

    This calculation does not account for correction due to site being on a slope.
    This is accounted for in a correction method.
    """

    name = "calc_albedo"
    inputs = ("swin", "swout")

    def solar_zenith(date_times: str, latitude: float) -> pl.Expr:
        """
        Calculate angle of the sun from the vertical
        Taken from https://en.wikipedia.org/wiki/Solar_zenith_angle, with some
        approximations
        """

        # Convert latitude to radians
        phi = latitude * math.pi / 180

        # Hour angle h (radians)
        h = (pl.col(date_times).dt.hour() + pl.col(date_times).dt.minute() / 60 - 12) * (2 * math.pi / 24)

        # Day of year (N)
        N = pl.col(date_times).dt.ordinal_day()

        # Declination delta (radians)
        delta = -(23.44 * math.pi / 180) * pl.cos((2 * math.pi / 365) * (N + 10))

        # cos(theta_s)
        cos_theta_s = pl.sin(phi) * pl.sin(delta) + pl.cos(phi) * pl.cos(delta) * pl.cos(h)

        # Return solar zenith angle in radians
        return pl.arccos(cos_theta_s)

    def expr(self, columns: dict[str, pl.Expr]) -> pl.Expr:
        """Calculate albedo [units = None] (fraction)
        Args:
            columns: Dict with keys of required columns for the calculation.
            - "swin": Shortwave incoming radiation [W m-2]
            - "swout": Shortwave outgoing radiation [" m-2]
        Returns:
            Polars expression computing albedo.
        """
        swin = columns["swin"]
        swout = columns["swout"]
        latitude = self.config.params["LATITUDE"]
        albedo = swout / swin

        # Remove night time values
        df = pl.DataFrame({"ALBEDO": albedo, "SWIN": swin})
        df["THETA_S"] = self.solar_zenith(df.index, latitude)

        # Calculate theoretical estimate of SWIN for clear sky
        df["SWIN_CLEAR"] = pl.cos(df["THETA_S"])
        # Eliminate "negative nightime SWIN"
        df.loc[df.SWIN_CLEAR <= 0, "ALBEDO"] = pl.nan

        albedo = df["ALBEDO"].copy()

        albedo[albedo < 0.0] = 0.0
        albedo[albedo > 1.0] = 1.0

        return albedo
