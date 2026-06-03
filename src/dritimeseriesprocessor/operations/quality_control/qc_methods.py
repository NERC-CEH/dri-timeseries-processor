from abc import ABC, abstractmethod
from datetime import datetime

import polars as pl
import time_stream as ts
from time_stream.operation import Operation

from dritimeseriesprocessor.models.domain_models.processing_config import DataProcessingMethodConfig
from dritimeseriesprocessor.utils.enums import ConfigurationType


def _observation_interval(config: DataProcessingMethodConfig) -> tuple[datetime, datetime | None] | None:
    if config.start_date is None:
        return None
    return config.start_date, config.end_date


class QcMethod(Operation, ABC):
    operation_type = ConfigurationType.QUALITY_CONTROL

    @abstractmethod
    def run(self, *args, **kwargs) -> pl.Series:
        pass


@QcMethod.register
class Range(QcMethod):
    name = "range"
    flag_value = 1  # TODO : should these be in metadata? - yes

    def run(self, tf: ts.TimeFrame, config: DataProcessingMethodConfig) -> pl.Series:
        return tf.qc_check(
            "range",
            max_value=config.params["gt"],
            min_value=config.params["lt"],
            within=False,
            column_name=tf.metadata["column_name"],
            observation_interval=_observation_interval(config),
        )


@QcMethod.register
class BatteryVoltage(QcMethod):
    name = "battery_v"
    flag_value = 2

    def run(self, tf: ts.TimeFrame, config: DataProcessingMethodConfig) -> pl.Series:
        return tf.qc_check(
            "comparison",
            operator="<",
            compare_to=config.params["lt"],
            column_name=tf.metadata["column_name"],
            observation_interval=_observation_interval(config),
        )


@QcMethod.register
class Samples(QcMethod):
    name = "samples"
    flag_value = 4

    def run(self, tf: ts.TimeFrame, config: DataProcessingMethodConfig) -> pl.Series:
        return tf.qc_check(
            "comparison",
            operator="<",
            compare_to=config.params["lt"],
            column_name=tf.metadata["column_name"],
            observation_interval=_observation_interval(config),
        )


@QcMethod.register
class ErrorCode(QcMethod):
    name = "error_code"
    flag_value = 8

    def run(self, tf: ts.TimeFrame, config: DataProcessingMethodConfig) -> pl.Series:
        return tf.qc_check(
            "comparison",
            operator="is_in",
            compare_to=config.params["value"],
            column_name=tf.metadata["column_name"],
            observation_interval=_observation_interval(config),
        )


@QcMethod.register
class Spike(QcMethod):
    name = "spike"
    flag_value = 16

    def run(self, tf: ts.TimeFrame, config: DataProcessingMethodConfig) -> pl.Series:
        return tf.qc_check(
            "spike",
            threshold=config.params["gt"],
            column_name=tf.metadata["column_name"],
            observation_interval=_observation_interval(config),
        )


@QcMethod.register
class Nr01Temp(QcMethod):
    name = "nr01_temp"
    flag_value = 32

    def run(self, tf: ts.TimeFrame, config: DataProcessingMethodConfig) -> pl.Series:
        return tf.qc_check(
            "range",
            max_value=config.params["gt"],
            min_value=config.params["lt"],
            within=False,
            column_name=tf.metadata["column_name"],
            observation_interval=_observation_interval(config),
        )


@QcMethod.register
class HeatFluxPlateRemoval(QcMethod):
    name = "hfp_removal"
    flag_value = 64

    def run(self, tf: ts.TimeFrame, config: DataProcessingMethodConfig) -> pl.Series:
        return tf.qc_check(
            "time_range",
            max_value=datetime.strptime(config.params["time_le"], "%H:%M:%S").time(),
            min_value=datetime.strptime(config.params["time_ge"], "%H:%M:%S").time(),
            within=True,
            closed="both",
            column_name=tf.metadata["column_name"],
            observation_interval=_observation_interval(config),
        )


@QcMethod.register
class PluvioDiagnostic(QcMethod):
    name = "pluvio_diag"
    flag_value = 128

    def run(self, tf: ts.TimeFrame, config: DataProcessingMethodConfig) -> pl.Series:
        return tf.qc_check(
            "comparison",
            operator=">",
            compare_to=config.params["gt"],
            column_name=tf.metadata["column_name"],
            observation_interval=_observation_interval(config),
        )


@QcMethod.register
class SnowDaySignal(QcMethod):
    name = "snowd_signal"
    flag_value = 256

    def run(self, tf: ts.TimeFrame, config: DataProcessingMethodConfig) -> pl.Series:
        return tf.qc_check(
            "comparison",
            operator="<",
            compare_to=config.params["lt"],
            column_name=tf.metadata["column_name"],
            observation_interval=_observation_interval(config),
        )


@QcMethod.register
class TdtTSoil(QcMethod):
    name = "tdt_tsoil"
    flag_value = 512

    def run(self, tf: ts.TimeFrame, config: DataProcessingMethodConfig) -> pl.Series:
        return tf.qc_check(
            "comparison",
            operator="<",
            compare_to=config.params["lt"],
            column_name=tf.metadata["column_name"],
            observation_interval=_observation_interval(config),
        )


@QcMethod.register
class FluxQcFlag(QcMethod):
    """Apply EddyPro's internal quality flag to a flux variable.

    Receives the qc-flag container's TimeFrame via dep_ts, so tf.df[col]
    is e.g. qc_H. Flag value 2 (poor quality) is always rejected.
    """

    name = "flux_qc_flag"
    flag_value = 1024

    def run(self, tf: ts.TimeFrame, config: DataProcessingMethodConfig) -> pl.Series:
        col = tf.metadata["column_name"]
        return tf.df[col] == 2
