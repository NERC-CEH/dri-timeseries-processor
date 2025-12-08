import logging

from new_processor.domain_models.time_series_container import TimeSeriesContainer
from new_processor.utils.enums import OperationType
from new_processor.operations.flags.flag_operations import update_quality_control_core_flags
from new_processor.operations.flags.flag_names import QC_FLAG_SYS_NAME, qc_flag_column_name
from new_processor.operations.operation_processor import OperationProcessor

logger = logging.getLogger(__name__)


class QCProcessor(OperationProcessor):
    """Processor for running Quality Control (QC) checks on a TimeSeriesContainer.
    """
    def __init__(self):
        super().__init__(OperationType.QUALITY_CONTROL, QC_FLAG_SYS_NAME)

    def get_configs(self, container: TimeSeriesContainer):
        return container.qc_configs

    def get_flag_column(self, column: str):
        return qc_flag_column_name(column)

    def apply_method(self, tf_primary, method_metadata, config, dataset_repository):
        params = config.params

        # Decide which TimeFrame to run QC against
        tf_qc = tf_primary
        if "dep_ts" in params:
            tf_qc = dataset_repository[params.pop("dep_ts")].data

        # Run QC
        result = tf_qc.qc_check(
            method_metadata.function_name,
            column_name=tf_qc.metadata["column_name"],
            observation_interval=(config.start_date, config.end_date),
            **params,
        )

        return result

    def compute_flag_mask(self, tf, result, column_name):
        """For QC, the flag mask is just the result of the qc check"""
        return result

    def core_flag_updater(self, tf):
        return update_quality_control_core_flags(tf)