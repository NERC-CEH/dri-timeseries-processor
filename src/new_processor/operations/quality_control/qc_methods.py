from abc import ABC, abstractmethod
from datetime import datetime

from new_processor.utils.enums import OperationType

from time_stream.operation import Operation


class QcMethod(Operation, ABC):
    operation_type: OperationType.QUALITY_CONTROL

    @abstractmethod
    def run(self, *args, **kwargs):
        pass


@QcMethod.register
class Range(QcMethod):
    name = "range"
    flag_value = 1

    def run(self, tf, config):
        return tf.qc_check(
            "range",
            max_value=config.params["gt"],
            min_value=config.params["lt"],
            within=False,
            column_name=tf.metadata["column_name"],
            observation_interval=(config.start_date, config.end_date),
        )


@QcMethod.register
class BatteryVoltage(QcMethod):
    name = "battery_v"
    flag_value = 2

    def run(self, tf, config):
        return tf.qc_check(
            "comparison",
            operator="<",
            compare_to=config.params["lt"],
            column_name=tf.metadata["column_name"],
            observation_interval=(config.start_date, config.end_date),
        )


@QcMethod.register
class Samples(QcMethod):
    name = "samples"
    flag_value = 4

    def run(self, tf, config):
        return tf.qc_check(
            "comparison",
            operator="<",
            compare_to=config.params["lt"],
            column_name=tf.metadata["column_name"],
            observation_interval=(config.start_date, config.end_date),
        )


@QcMethod.register
class ErrorCode(QcMethod):
    name = "error_code"
    flag_value = 8

    def run(self, tf, config):
        return tf.qc_check(
            "comparison",
            operator="is_in",
            compare_to=config.params["value"],
            column_name=tf.metadata["column_name"],
            observation_interval=(config.start_date, config.end_date),
        )


@QcMethod.register
class Spike(QcMethod):
    name = "spike"
    flag_value = 16

    def run(self, tf, config):
        return tf.qc_check(
            "spike",
            threshold=config.params["gt"],
            column_name=tf.metadata["column_name"],
            observation_interval=(config.start_date, config.end_date),
        )


@QcMethod.register
class Nr01Temp(QcMethod):
    name = "nr01_temp"
    flag_value = 32

    def run(self, tf, config):
        return tf.qc_check(
            "range",
            max_value=config.params["gt"],
            min_value=config.params["lt"],
            within=False,
            column_name=tf.metadata["column_name"],
            observation_interval=(config.start_date, config.end_date),
        )


@QcMethod.register
class HeatFluxPlateRemoval(QcMethod):
    name = "hfp_removal"
    flag_value = 64

    def run(self, tf, config):
        return tf.qc_check(
            "time_range",
            max_value=datetime.strptime(config.params["time_le"], "%H:%M:%S").time(),
            min_value=datetime.strptime(config.params["time_ge"], "%H:%M:%S").time(),
            within=True,
            closed="both",
            column_name=tf.metadata["column_name"],
            observation_interval=(config.start_date, config.end_date),
        )


@QcMethod.register
class PluvioDiagnostic(QcMethod):
    name = "pluvio_diag"
    flag_value = 128

    def run(self, tf, config):
        return tf.qc_check(
            "comparison",
            operator=">",
            compare_to=config.params["gt"],
            column_name=tf.metadata["column_name"],
            observation_interval=(config.start_date, config.end_date),
        )


@QcMethod.register
class SnowDaySignal(QcMethod):
    name = "snowd_signal"
    flag_value = 256

    def run(self, tf, config):
        return tf.qc_check(
            "comparison",
            operator="<",
            compare_to=config.params["lt"],
            column_name=tf.metadata["column_name"],
            observation_interval=(config.start_date, config.end_date),
        )


@QcMethod.register
class TdtTSoil(QcMethod):
    name = "tdt_tsoil"
    flag_value = 512

    def run(self, tf, config):
        return tf.qc_check(
            "comparison",
            operator="<",
            compare_to=config.params["lt"],
            column_name=tf.metadata["column_name"],
            observation_interval=(config.start_date, config.end_date),
        )
