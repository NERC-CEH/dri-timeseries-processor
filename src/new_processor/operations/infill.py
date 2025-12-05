import logging

from new_processor.routers.metadata_router import load_methods
from new_processor.domain_models.time_series_container import TimeSeriesContainer
from new_processor.utils.enums import OperationType
from new_processor.operations.flags.flag_operations import update_infill_core_flags
from new_processor.operations.flags.flag_names import INFILL_FLAG_SYS_NAME, infill_flag_column_name
from new_processor.operations.operation_processor import OperationProcessor

logger = logging.getLogger(__name__)


class InfillProcessor(OperationProcessor):
    """Processor for running infilling on a TimeSeriesContainer.
    """
    def __init__(self):
        operation_type = OperationType.INFILLING
        registry = load_methods(operation_type)
        super().__init__(operation_type, INFILL_FLAG_SYS_NAME, registry)

    def get_configs(self, container: TimeSeriesContainer):
        return container.infill_configs

    def get_flag_column(self, column: str):
        return infill_flag_column_name(column)

    def sort_configs(self, configs):
        """Infill configs have a required priority ordering
        """
        return sorted(configs, key=lambda cfg: cfg.annotations.get("priority", 0))

    def apply_method(self, tf_primary, method_metadata, config, dataset_repository):
        params = config.params.copy()  # ensure we don't mutate original parameters
        infill_column = tf_primary.metadata["column_name"]

        # TODO: Unsure whether this parameter is actually needed.  Not used in any method currently.
        params.pop("window", None)

        # Collect any dependency TimeFrame to run infill with
        if "dep_ts" in params:
            dep_id = params.pop("dep_ts")

            if dep_id not in dataset_repository:
                raise LookupError(f"Dependency time series {dep_id} not found.")

            dep_tf = dataset_repository[dep_id].data
            params["alt_df"] = dep_tf.df
            params["alt_data_column"] = dep_tf.metadata["column_name"]

        # Apply infilling method
        result = tf_primary.infill(
            method_metadata.function_name,
            infill_column,
            observation_interval=(config.start_date, config.end_date),
            **params,
        )

        return result

    def compute_flag_mask(self, tf, result, column_name):
        before_mask = tf.df[column_name].is_null()
        after_mask = result.df[column_name].is_null()
        return before_mask.ne(after_mask)

    def core_flag_updater(self, tf):
        return update_infill_core_flags(tf)