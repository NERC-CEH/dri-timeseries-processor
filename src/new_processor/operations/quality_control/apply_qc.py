import logging

from time_stream.exceptions import FlagSystemNotFoundError

from new_processor.domain_models.time_series_container import TimeSeriesContainer
from new_processor.routers.metadata_router import load_qc_methods
from new_processor.operations.flags.flag_operations import update_quality_control_core_flags
from new_processor.operations.flags.flag_names import QC_FLAG_SYS_NAME, qc_flag_column_name

logger = logging.getLogger(__name__)


def run_quality_control(container: TimeSeriesContainer, dataset_repository):
    """Apply QC methods to a single TimeFrame.
    """
    registry = load_qc_methods()
    methods = registry.items
    tf_primary = container.data
    col_primary = tf_primary.metadata["column_name"]

    # Ensure QC flag system exists
    flag_system = {name: m.id for name, m in methods.items()}
    try:
        tf_primary.get_flag_system(QC_FLAG_SYS_NAME)
    except FlagSystemNotFoundError:
        tf_primary.register_flag_system(QC_FLAG_SYS_NAME, flag_system)

    # Prepare QC flag column
    qc_flag_col = qc_flag_column_name(col_primary)
    if qc_flag_col not in tf_primary.flag_columns:
        tf_primary.init_flag_column(col_primary, QC_FLAG_SYS_NAME, qc_flag_col)

    # Apply each QC config
    for qc_config in container.qc_configs:
        for qc_method_config in qc_config.method_configs:

            logger.info(
                f"Quality controlling {container.ts_id}: {qc_method_config.method}. "
                f"Constraints: {qc_method_config.params}"
            )

            method = methods[qc_method_config.method]

            # Decide which TimeFrame to run QC against
            tf_qc = tf_primary
            if "dep_ts" in qc_method_config.params:
                tf_qc = dataset_repository[qc_method_config.params.pop("dep_ts")].data

            # Map parameter names
            params = qc_method_config.params.copy()
            for old, new in method.arg_mapping.items():
                params[new] = params.pop(old)

            # Add default kwargs
            params.update(method.kwargs)

            # Run QC
            result = tf_qc.qc_check(
                method.function_name,
                column_name=tf_qc.metadata["column_name"],
                observation_interval=(qc_method_config.start_date, qc_method_config.end_date),
                **params,
            )

            # Flag the primary TimeFrame
            # TODO: Update TimeFrame to accept boolean pl.series as the expr
            tf_primary.add_flag(qc_flag_col, qc_method_config.method, result)  # type: ignore[arg-type]

    # Update core flags
    tf_primary = update_quality_control_core_flags(tf_primary)

    return tf_primary