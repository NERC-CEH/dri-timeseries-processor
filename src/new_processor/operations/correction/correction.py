import logging

from new_processor.routers.metadata_router import load_methods
from new_processor.domain_models.time_series_container import TimeSeriesContainer
from new_processor.utils.enums import OperationType
from new_processor.operations.flags.flag_operations import update_corrections_core_flags
from new_processor.operations.flags.flag_names import CORRS_FLAG_SYS_NAME, corrs_flag_column_name
from new_processor.operations.operation_processor import OperationProcessor
from new_processor.operations.correction.correction_operations import Correction

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
        params = config.params
        correction_column = tf_primary.metadata["column_name"]

        # Name any dependent timeseries with their column names
        if params.get("dep_ts"):
            dep_ids = params.pop("dep_ts")

            if isinstance(dep_ids, str):
                dep_ids = [dep_ids]

            for dep_id in dep_ids:
                if dep_id not in dataset_repository:
                    raise LookupError(f"Dependency time series {dep_id} not found.")

                dep_tf = dataset_repository[dep_id].data
                dep_name = dep_tf.metadata["column_name"].lower()
                params[dep_name] = dep_tf

            # Rename params again as the dep ts IDs may need to be renamed
            #   (e.g. lwout_unc and lwin_unc rename to lw_unc in the lw_corr correction)
            params = self.configure_parameters(method_metadata, params)

        # Apply the correction
        correction = Correction.get(method_metadata.function_name, **params)
        result = tf_primary.with_df(
            correction.apply(
                tf_primary.df,
                tf_primary.time_name,
                correction_column,
                observation_interval=(config.start_date, config.end_date),
            )
        )

        return result

    def compute_flag_mask(self, tf, result, column_name):
        before_mask = tf.df[column_name].is_null()
        after_mask = result.df[column_name].is_null()
        return before_mask.ne(after_mask)

    def core_flag_updater(self, tf):
        return update_corrections_core_flags(tf)