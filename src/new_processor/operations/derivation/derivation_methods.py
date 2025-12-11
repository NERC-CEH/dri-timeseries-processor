from abc import ABC, abstractmethod

import polars as pl
import time_stream as ts
from time_stream.operation import Operation

from new_processor.models.domain_models.processing_config import ProcessingMethodConfig
from new_processor.utils.enums import OperationType
from new_processor.utils.time_stream_utils import merge_multiple_timeframes


class DerivationMethod(Operation, ABC):
    operation_type: OperationType.DERIVATION

    @abstractmethod
    def run(self, *args, **kwargs) -> ts.TimeFrame:
        pass


@DerivationMethod.register
class NetRadiation(DerivationMethod):
    """Calculate net radiation:

    RN = SWIN - SWOUT + LWIN - LWOUT

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

    name = "calculate-calculate_rn"

    def run(self, config: ProcessingMethodConfig) -> ts.TimeFrame:
        """Run net radiation calculation

        Args:
            config: Configuration parameters to run this method.

        Returns:
            Resulting TimeFrame.
        """
        tf_map: dict[str, ts.TimeFrame] = {name: config.params[name] for name in ("swin", "swout", "lwin", "lwout")}

        merged_tf = merge_multiple_timeframes(list(tf_map.values()))
        time_name = merged_tf.time_name

        # Extract required config
        output_col = config.params["output_col"]
        resolution = config.params["resolution"]
        periodicity = config.params["periodicity"]

        swin_col = pl.col(tf_map["swin"].metadata["column_name"])
        swout_col = pl.col(tf_map["swout"].metadata["column_name"])
        lwin_col = pl.col(tf_map["lwin"].metadata["column_name"])
        lwout_col = pl.col(tf_map["lwout"].metadata["column_name"])

        # Do the calculation
        result = merged_tf.df.with_columns((swin_col - swout_col + lwin_col - lwout_col).alias(output_col))

        # Create and return TimeFrame with the result
        return ts.TimeFrame(
            df=result, time_name=time_name, resolution=resolution, periodicity=periodicity
        ).with_metadata({"column_name": output_col})


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
        "g1": <TimeFrame> Soil heat flux density [MJ m-2 30min-1]
        "g2": <TimeFrame> Soil heat flux density [MJ m-2 30min-1]
        "ta": <TimeFrame> Air temperature [degC]
        "rh": <TimeFrame> Relative humidity [%]
        "ws": <TimeFrame> Wind speed at 2m height [ms-1]
        "pa": <TimeFrame> Atmospheric pressure [kPa]
        "output_col": <str> Required name of output
        "resolution": <str> Expected output resolution
        "periodicity": <str> Expected output periodicity
    }
    """

    name = "calculate-calculate_pe"

    def run(self, config: ProcessingMethodConfig) -> ts.TimeFrame:
        tf_map: dict[str, ts.TimeFrame] = {
            name: config.params[name] for name in ("rn", "g1", "g2", "ta", "rh", "ws", "pa")
        }

        merged_tf = merge_multiple_timeframes(list(tf_map.values()))
        time_name = merged_tf.time_name

        # Extract required config
        output_col = config.params["output_col"]
        resolution = config.params["resolution"]
        periodicity = config.params["periodicity"]

        rn_col = pl.col(tf_map["rn"].metadata["column_name"])
        g1_col = pl.col(tf_map["g1"].metadata["column_name"])
        g2_col = pl.col(tf_map["g2"].metadata["column_name"])
        ta_col = pl.col(tf_map["ta"].metadata["column_name"])
        rh_col = pl.col(tf_map["rh"].metadata["column_name"])
        ws_col = pl.col(tf_map["ws"].metadata["column_name"])
        pa_col = pl.col(tf_map["pa"].metadata["column_name"])

        # Soil heat flux: average of g1 and g2
        # TODO: Is this a COSMOS specific thing that we have two G columns?
        g = pl.mean_horizontal(g1_col, g2_col)

        # Saturation vapour pressure (es)
        # Steps taken from FAO-56 method (eq11) https://www.fao.org/4/x0490e/x0490e07.htm#calculation%20procedures
        es = 0.6108 * ((17.27 * ta_col) / (ta_col + 237.3)).exp()

        # Actual vapour pressure (ea)
        # Steps taken from FAO-56 1-hour method (eq54) https://www.fao.org/4/x0490e/x0490e08.htm
        ea = es * (rh_col / 100)

        # Vapour pressure deficit
        vpd = es - ea

        # Slope of vapour pressure curve (delta)
        # Steps taken from FAO-56 method (eq13) https://www.fao.org/4/x0490e/x0490e07.htm#calculation%20procedures
        delta = (4098 * es) / ((ta_col + 237.3) ** 2)

        # Latent heat of vaporization (MJ/kg)
        # Steps taken from Harrison (1963), referenced by FAO Annex 3 https://www.fao.org/4/x0490e/x0490e0k.htm
        #
        #         Harrison, L.P. 1963. "Fundamental concepts and definitions relating to humidity."
        #             In: Wexler, A. & Wildhack, W.A. (eds.) Humidity and Moisture. Vol. 3.
        #             Reinhold Publishing Company, New York
        lv = 2.501 - (2.361e-3 * ta_col)

        # Psychrometric constant (gamma)
        # Steps taken from FAO-56 method (eq8) https://www.fao.org/4/x0490e/x0490e07.htm#psychrometric%20constant%20(g)
        cp = 1.013e-3
        e_ratio = 0.622
        gamma = (cp * (pa_col / 10)) / (e_ratio * lv)

        # Convert wind speed to 2m height
        # Steps taken from FAO-56 method (eq47) https://www.fao.org/4/x0490e/x0490e07.htm#wind%20profile%20relationship
        # TODO: get wind height from metadata
        wind_height = 2.6
        ws_2m = ws_col * (4.87 / pl.ln((67.8 * wind_height) - 5.42))

        # Convert RN and G from W/m2 - MJ per 30 min (if upstream provides W/m2)
        # TODO: How do we know this needs doing? Interrogate units in metadata?
        rn_mj = rn_col * 0.0018
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
        aerodynamic_term = gamma * (reference_crop_type_numerator / (ta_col + 273)) * ws_2m * vpd
        resistance_term = delta + gamma * (1 + (reference_crop_type_denominator * ws_2m))

        pet_expr = (radiation_term + aerodynamic_term) / resistance_term

        # Do the final calculation
        result = merged_tf.df.with_columns(pet_expr.alias(output_col))

        # Create and return TimeFrame with the result
        return ts.TimeFrame(
            df=result, time_name=time_name, resolution=resolution, periodicity=periodicity
        ).with_metadata({"column_name": output_col})
