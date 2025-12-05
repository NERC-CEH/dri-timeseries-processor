import logging

from time_stream.exceptions import FlagSystemNotFoundError

from new_processor.domain_models.time_series_container import TimeSeriesContainer
from new_processor.routers.metadata_router import load_correction_methods
from new_processor.operations.flags.flag_operations import update_corrections_core_flags
from new_processor.operations.flags.flag_names import CORRS_FLAG_SYS_NAME, corrs_flag_column_name

logger = logging.getLogger(__name__)


def run_corrections(container: TimeSeriesContainer, dataset_repository):
    """Apply correction methods to a single TimeFrame.
    """
    registry = load_correction_methods()
    correction_methods = registry.items
    tf_primary = container.data
    col_primary = tf_primary.metadata["column_name"]

    # Ensure correction flag system exists
    flag_system = {name: m.id for name, m in correction_methods.items()}
    try:
        tf_primary.get_flag_system(CORRS_FLAG_SYS_NAME)
    except FlagSystemNotFoundError:
        tf_primary.register_flag_system(CORRS_FLAG_SYS_NAME, flag_system)

    # Prepare correction flag column
    corrs_flag_col = corrs_flag_column_name(col_primary)
    if corrs_flag_col not in tf_primary.flag_columns:
        tf_primary.init_flag_column(col_primary, CORRS_FLAG_SYS_NAME, corrs_flag_col)

    # Apply each correction
    for correction_config in container.correction_configs:
        for correction_method_config in correction_config.method_configs:

            logger.info(
                f"Correcting {container.ts_id}: {correction_method_config.method}. "
                f"Constraints: {correction_method_config.params}"
            )