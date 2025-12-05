import logging

from new_processor.routers.metadata_router import load_methods
from new_processor.domain_models.time_series_container import TimeSeriesContainer
from new_processor.utils.enums import OperationType
from new_processor.operations.flags.flag_operations import update_corrections_core_flags
from new_processor.operations.flags.flag_names import CORRS_FLAG_SYS_NAME, corrs_flag_column_name
from new_processor.operations.operation_processor import OperationProcessor

logger = logging.getLogger(__name__)


class CorrectionProcessor(OperationProcessor):
    """Processor for running corrections on a TimeSeriesContainer.
    """
    def __init__(self):
        operation_type = OperationType.CORRECTION
        registry = load_methods(operation_type)
        super().__init__(operation_type, CORRS_FLAG_SYS_NAME, registry)

    def get_configs(self, container: TimeSeriesContainer):
        return container.correction_configs

    def get_flag_column(self, column: str):
        return corrs_flag_column_name(column)

    def apply_method(self, tf_primary, method_metadata, config, dataset_repository):
        params = config.params.copy()  # ensure we don't mutate original parameters
        correction_column = tf_primary.metadata["column_name"]

        #return result

    def compute_flag_mask(self, tf, result, column_name):
        #before_mask = tf.df[column_name].is_null()
        #after_mask = result.df[column_name].is_null()
        #return before_mask.ne(after_mask)
        pass

    def core_flag_updater(self, tf):
        return update_corrections_core_flags(tf)