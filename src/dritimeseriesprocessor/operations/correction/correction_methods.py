import math
from abc import ABC, abstractmethod

import polars as pl
import time_stream as ts
from time_stream.operation import Operation
from time_stream.utils import get_date_filter

from dritimeseriesprocessor.models.domain_models.processing_config import DataProcessingMethodConfig
from dritimeseriesprocessor.utils.enums import OperationType
from dritimeseriesprocessor.utils.time_stream_utils import merge_multiple_timeframes


class CorrectionMethod(Operation, ABC):
    operation_type: OperationType.CORRECTION

    @abstractmethod
    def run(self, *args, **kwargs) -> ts.TimeFrame:
        pass


@CorrectionMethod.register
class Add(CorrectionMethod):
    """Add operation class."""

    name = "add"
    flag_value = 1

    def run(self, tf: ts.TimeFrame, config: DataProcessingMethodConfig) -> ts.TimeFrame:
        date_filter = get_date_filter(tf.time_name, (config.start_date, config.end_date))
        return tf.with_df(
            tf.df.with_columns(
                pl.when(date_filter)
                .then(pl.col(tf.metadata["column_name"]) + config.params["correction_factor"])
                .otherwise(pl.col(tf.metadata["column_name"]))
            )
        )


@CorrectionMethod.register
class LWCorrection(CorrectionMethod):
    """Long wave correction operation class."""

    name = "lw_corr"
    flag_value = 2

    def run(self, tf: ts.TimeFrame, config: DataProcessingMethodConfig) -> ts.TimeFrame:
        lw_unc_tf = self._get_lw_unc(config)
        ta_tf = config.params["ta"]

        lw_unc_col = lw_unc_tf.metadata["column_name"]
        ta_col = ta_tf.metadata["column_name"]

        # First correct the uncalibrated values.
        lw_unc_corr = lw_unc_tf.df.with_columns(pl.col(lw_unc_col) * config.params["correction_factor"])

        # Now re-calibrate LW value with temperature adjustment.
        # Convert temperature to Kelvin
        ta_k = ta_tf.df.with_columns(pl.col(ta_col) + 273.15)

        # Get adjustment amount from Stefan-Boltzmann constant 5.67 * 10^-8
        sb_adj = ta_k.with_columns((pl.col(ta_col).pow(4) * 5.67 * 1e-8).alias("SB_adj")).select("SB_adj")

        # Recalculate LW value
        date_filter = get_date_filter(tf.time_name, (config.start_date, config.end_date))
        return tf.with_df(
            tf.df.with_columns(
                pl.when(date_filter)
                .then((lw_unc_corr[lw_unc_col] + sb_adj["SB_adj"]).alias(tf.metadata["column_name"]))
                .otherwise(pl.col(tf.metadata["column_name"]))
            )
        )

    @staticmethod
    def _get_lw_unc(config: DataProcessingMethodConfig) -> ts.TimeFrame:
        """Retrieve the longwave radiation uncorrected (lw_unc) TimeFrame from processing configuration.

        This supports processing methods that operate on either LWIN or LWOUT datasets, each of which depends on
        a corresponding uncorrected time series (LWIN_UNC or LWOUT_UNC). To keep downstream logic generic,
        this function resolves exactly one of these parameters and returns it as the longwave uncertainty input.

        Args:
            config: Configuration of the correction method.

        Returns:
            The lw_unc TimeFrame corresponding to either LWIN_UNC or LWOUT_UNC
        """
        possible_keys = {"lwin_unc", "lwout_unc"}
        found_keys = possible_keys & config.params.keys()

        if len(found_keys) != 1:
            raise KeyError(f"Expected exactly one of {possible_keys}, found {found_keys}")

        return config.params[found_keys.pop()]


@CorrectionMethod.register
class Scalar(CorrectionMethod):
    """Scalar operation class."""

    name = "scalar"
    flag_value = 4

    def run(self, tf: ts.TimeFrame, config: DataProcessingMethodConfig) -> ts.TimeFrame:
        date_filter = get_date_filter(tf.time_name, (config.start_date, config.end_date))
        return tf.with_df(
            tf.df.with_columns(
                pl.when(date_filter)
                .then(pl.col(tf.metadata["column_name"]) * config.params["correction_factor"])
                .otherwise(pl.col(tf.metadata["column_name"]))
            )
        )


@CorrectionMethod.register
class PACorrection(CorrectionMethod):
    """Correct air pressure with bias calculated from mean sea level pressure."""

    name = "pa_corr"
    flag_value = 8

    def run(self, tf: ts.TimeFrame, config: DataProcessingMethodConfig) -> ts.TimeFrame:
        ta_tf = config.params["ta"]

        primary_col = tf.metadata["column_name"]
        ta_col = ta_tf.metadata["column_name"]

        altitude = config.params["altitude"]

        pa_corr = ta_tf.df.with_columns(
            (
                config.params["correction_factor"]
                * (1 - ((0.0065 * altitude) / (pl.col(ta_col) + (0.0065 * altitude) + 273.15))) ** 5.257
            ).alias("pa_corr")
        )

        date_filter = get_date_filter(tf.time_name, (config.start_date, config.end_date))
        return tf.with_df(
            tf.df.with_columns(
                pl.when(date_filter)
                .then(pl.col(primary_col) + pa_corr["pa_corr"])
                .otherwise(pl.col(primary_col))
                .alias(primary_col)
            )
        )


@CorrectionMethod.register
class Power(CorrectionMethod):
    """Power operation class."""

    name = "power"
    flag_value = 16

    def run(self, tf: ts.TimeFrame, config: DataProcessingMethodConfig) -> ts.TimeFrame:
        date_filter = get_date_filter(tf.time_name, (config.start_date, config.end_date))
        return tf.with_df(
            tf.df.with_columns(
                pl.when(date_filter)
                .then(pl.col(tf.metadata["column_name"]).pow(config.params["correction_factor"]))
                .otherwise(pl.col(tf.metadata["column_name"]))
            )
        )


@CorrectionMethod.register
class WDCorrection(CorrectionMethod):
    """Wind direction correction operation class."""

    name = "wd"
    flag_value = 32

    def run(self, tf: ts.TimeFrame, config: DataProcessingMethodConfig) -> ts.TimeFrame:
        ux_tf = config.params["ux"]
        uy_tf = config.params["uy"]
        merged_tf = merge_multiple_timeframes([ux_tf, uy_tf])

        primary_col = tf.metadata["column_name"]
        ux_col = ux_tf.metadata["column_name"]
        uy_col = uy_tf.metadata["column_name"]

        # Core WD correction expression
        wd_expr = (180.0 / pl.lit(math.pi)) * pl.arctan2(pl.col(ux_col), pl.col(uy_col)) + 90.0

        # Wrap negatives into [0, 360)
        wd_wrapped = pl.when(wd_expr < 0.0).then(wd_expr + 360.0).otherwise(wd_expr)

        # Calculate and round to 5 decimal places
        wd_corr = merged_tf.df.with_columns(wd_wrapped.round(5).alias(primary_col))[primary_col]

        return tf.with_df(tf.df.with_columns(wd_corr.alias(primary_col)))


@CorrectionMethod.register
class Clip(CorrectionMethod):
    """
    Sets all values above or below a given value to that value.
    config.params["max"] is the value the data should be clipped at from above.
    config.params["min"] is the value the data should be clipped at from below.
    Example:
    config.params["max"] = None
    config.params["min"] = 0
    => data below 0 is set to 0
    Used for e.g. PE.
    """

    name = "clip"
    flag_value = 64

    def run(self, tf: ts.TimeFrame, config: DataProcessingMethodConfig) -> ts.TimeFrame:
        col_name = tf.metadata["column_name"]

        min_threshold = config.params.get("min")
        max_threshold = config.params.get("max")

        if min_threshold is None and max_threshold is None:
            raise ValueError("Missing metadata parameter. At least one threshold must be specified in Clip method")

        # Return when date filter is promoted to an abstract method:
        # tf_clipped = tf.with_df(tf.df.with_columns(pl.col(col_name).clip(min_threshold, max_threshold)))

        date_filter = get_date_filter(tf.time_name, (config.start_date, config.end_date))

        return tf.with_df(
            tf.df.with_columns(
                pl.when(date_filter)
                .then(pl.col(col_name).clip(min_threshold, max_threshold))
                .otherwise(pl.col(col_name))
            )
        )


@CorrectionMethod.register
class AlbedoSouthSlopeCorrection(CorrectionMethod):
    """
    For sites on a slope, correct the albedo according to the angle of slope
    and the angle of the sun (according to the time of year).
    Valid on southerly aspects around solar noon only.
    s_max and s_min_fc should be the same across all UK sites, so are hardcoded here.
    """

    name = "albedo_south_slope_correction"
    flag_value = 128

    def run(self, tf: ts.TimeFrame, config: DataProcessingMethodConfig) -> ts.TimeFrame:
        s_max = 1200
        s_min_fc = 0.333333

        swin_tf = config.params["swin"]
        theta_s_tf = config.params["solar_zenith"]
        theta_g = config.params.get("theta_g")

        primary_col = tf.metadata["column_name"]
        swin_col = swin_tf.metadata["column_name"]
        theta_s_col = theta_s_tf.metadata["column_name"]

        swin_expr = swin_tf.df[swin_col]
        theta_s_expr = theta_s_tf.df[theta_s_col]

        # Calculate theoretical estimate of SWIN for clear sky
        swin_clear_expr = s_max * theta_s_expr.cos()

        # Beta varies from 1 on clear days, to 0 if SWIN is less than s_min_fac
        beta_expr = ((swin_expr - s_min_fc * swin_clear_expr) / ((1 - s_min_fc) * swin_clear_expr)).clip(0, 1)

        date_filter = get_date_filter(tf.time_name, (config.start_date, config.end_date))
        return tf.with_df(
            tf.df.with_columns(
                pl.when(date_filter)
                .then(
                    (
                        pl.col(primary_col)
                        * (1 - beta_expr + beta_expr * theta_s_expr.cos())
                        / (theta_s_expr - theta_g).cos()
                    ).clip(0, 1)
                )
                .otherwise(pl.col(primary_col))
            )
        )
