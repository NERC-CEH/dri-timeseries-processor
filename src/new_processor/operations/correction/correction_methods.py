from abc import ABC, abstractmethod

import polars as pl
import time_stream as ts
from time_stream.operation import Operation
from time_stream.utils import get_date_filter

from new_processor.models.domain_models.processing_config import ProcessingMethodConfig
from new_processor.utils.enums import OperationType


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

    # TODO: Should we pass the container into these methods rather than just the tf ?
    def run(self, tf: ts.TimeFrame, config: ProcessingMethodConfig) -> ts.TimeFrame:
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

    def run(self, tf: ts.TimeFrame, config: ProcessingMethodConfig) -> ts.TimeFrame:
        lw_unc_tf = config.params["lw_unc"]
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


@CorrectionMethod.register
class Scalar(CorrectionMethod):
    """Scalar operation class."""

    name = "scalar"
    flag_value = 4

    def run(self, tf: ts.TimeFrame, config: ProcessingMethodConfig) -> ts.TimeFrame:
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

    def run(self, tf: ts.TimeFrame, config: ProcessingMethodConfig) -> ts.TimeFrame:
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

    def run(self, tf: ts.TimeFrame, config: ProcessingMethodConfig) -> ts.TimeFrame:
        date_filter = get_date_filter(tf.time_name, (config.start_date, config.end_date))
        return tf.with_df(
            tf.df.with_columns(
                pl.when(date_filter)
                .then(pl.col(tf.metadata["column_name"]).pow(config.params["correction_factor"]))
                .otherwise(pl.col(tf.metadata["column_name"]))
            )
        )


# TODO: Placeholder implementation
@CorrectionMethod.register
class WDCorrection(CorrectionMethod):
    """Wind direction correction operation class."""

    name = "wd"
    flag_value = 32

    def run(self, tf: ts.TimeFrame, config: ProcessingMethodConfig) -> ts.TimeFrame:
        pass
