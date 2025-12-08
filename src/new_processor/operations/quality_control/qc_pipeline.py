import logging

import time_stream as ts

from new_processor.models.domain_models.processing_config import MethodConfig, ProcessingConfig
from new_processor.models.domain_models.time_series_container import TimeSeriesContainer
from new_processor.operations.flags.flag_methods import update_quality_control_core_flags
from new_processor.operations.flags.flag_names import QC_FLAG_SYS_NAME, qc_flag_column_name
from new_processor.operations.operation_pipeline import OperationPipeline
from new_processor.operations.quality_control.qc_methods import QcMethod
from new_processor.utils.enums import OperationType

logger = logging.getLogger(__name__)


class QCPipeline(OperationPipeline):
    """Pipeline for running Quality Control (QC) checks on a TimeSeriesContainer."""

    def __init__(self):
        super().__init__(OperationType.QUALITY_CONTROL, QC_FLAG_SYS_NAME)

    def get_configs(self, container: TimeSeriesContainer) -> set[ProcessingConfig]:
        return container.qc_configs

    def get_flag_column(self, column: str) -> str:
        return qc_flag_column_name(column)

    def compute_flag_mask(self, tf: ts.TimeFrame, result: ts.TimeFrame, column_name: str) -> ts.TimeFrame:
        """For QC, the flag mask is just the result of the qc check"""
        return result

    def core_flag_updater(self, tf: ts.TimeFrame) -> ts.TimeFrame:
        return update_quality_control_core_flags(tf)

    def apply_method(self, tf: ts.TimeFrame, config: MethodConfig, dataset_repository: dict) -> ts.TimeFrame:
        # Decide which TimeFrame to run QC against
        tf_qc = tf
        if "dep_ts" in config.params:
            tf_qc = dataset_repository[config.params["dep_ts"]].data

        method = QcMethod.get(config.method)
        return method.run(tf_qc, config)
