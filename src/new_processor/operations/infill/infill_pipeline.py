import logging

from new_processor.models.domain_models.time_series_container import TimeSeriesContainer
from new_processor.utils.enums import OperationType
from new_processor.operations.flags.flag_methods import update_infill_core_flags
from new_processor.operations.flags.flag_names import INFILL_FLAG_SYS_NAME, infill_flag_column_name
from new_processor.operations.operation_pipeline import OperationPipeline
from new_processor.operations.infill.infill_methods import InfillMethod

logger = logging.getLogger(__name__)


class InfillPipeline(OperationPipeline):
    """Processor for running infilling on a TimeSeriesContainer."""

    def __init__(self):
        super().__init__(OperationType.INFILLING, INFILL_FLAG_SYS_NAME)

    def get_configs(self, container: TimeSeriesContainer):
        return container.infill_configs

    def get_flag_column(self, column: str):
        return infill_flag_column_name(column)

    def sort_configs(self, configs):
        """Infill configs have a required priority ordering"""
        return sorted(configs, key=lambda cfg: cfg.annotations.get("priority", 0))

    def compute_flag_mask(self, tf, result, column_name):
        before_mask = tf.df[column_name].is_null()
        after_mask = result.df[column_name].is_null()
        return before_mask.ne(after_mask)

    def core_flag_updater(self, tf):
        return update_infill_core_flags(tf)

    def apply_method(self, tf, config, dataset_repository):
        # Collect any dependency TimeFrame to run infill with
        if "dep_ts" in config.params:
            dep_tf = dataset_repository[config.params["dep_ts"]].data
            config.params["alt_df"] = dep_tf.df
            config.params["alt_data_column"] = dep_tf.metadata["column_name"]

        method = InfillMethod.get(config.method)
        return method.run(tf, config)
