import logging

from new_processor.models.domain_models.time_series_container import TimeSeriesContainer
from new_processor.utils.enums import OperationType
from new_processor.operations.flags.flag_methods import update_corrections_core_flags
from new_processor.operations.flags.flag_names import CORRS_FLAG_SYS_NAME, corrs_flag_column_name
from new_processor.operations.operation_pipeline import OperationPipeline
from new_processor.operations.correction.correction_methods import CorrectionMethod


logger = logging.getLogger(__name__)


class CorrectionPipeline(OperationPipeline):
    """Processor for running corrections on a TimeSeriesContainer."""

    def __init__(self):
        super().__init__(OperationType.CORRECTION, CORRS_FLAG_SYS_NAME)

    def get_configs(self, container: TimeSeriesContainer):
        return container.correction_configs

    def get_flag_column(self, column: str):
        return corrs_flag_column_name(column)

    def apply_method(self, tf, config, dataset_repository):
        params = config.params

        # Name any dependent timeseries with their column names
        if "dep_ts" in config.params:
            dep_ids = config.params["dep_ts"]
            if isinstance(dep_ids, str):
                dep_ids = [dep_ids]

            for dep_id in dep_ids:
                dep_tf = dataset_repository[dep_id].data
                dep_name = dep_tf.metadata["column_name"].lower()

                # TODO - I think we should rename "dep_ts" in the config to "lw_unc" (in this example)
                if config.method == "lw_corr":
                    if dep_name in ["lwout_unc", "lwin_unc"]:
                        dep_name = "lw_unc"

                params[dep_name] = dep_tf

        method = CorrectionMethod.get(config.method)
        return method.run(tf, config)

    def compute_flag_mask(self, tf, result, column_name):
        before_mask = tf.df[column_name].is_null()
        after_mask = result.df[column_name].is_null()
        return before_mask.ne(after_mask)

    def core_flag_updater(self, tf):
        return update_corrections_core_flags(tf)
