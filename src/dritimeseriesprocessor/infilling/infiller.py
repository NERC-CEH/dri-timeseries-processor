import logging

from metadata_manager.models.service import load_config, load_methods
from time_series import TimeSeries

logger = logging.getLogger(__name__)


INFILL_FLAG_SYS_NAME = "infill_flags"
INFILL_CONFIGS = load_config("infilling")
INFILL_METHODS = load_methods("infilling")


def infill_flag_column_name(column: str) -> str:
    """
    Return column name of infill flag column for a given variable column.

    Args:
        column (str): The name of the original variable column.

    Returns:
        str: The name of the corresponding infill flag column, formatted as '{column}_INFILL_FLAG'.
    """
    return f"{column}_INFILL_FLAG"


def run_infilling(ts: TimeSeries, site_id: str) -> TimeSeries:
    """Run data through Infilling.

    Reads and applies infill methods for each variable from config.

    Args:
        ts: The input TimeSeries containing the data to be infilled.
        site_id: The site ID being processed.

    Returns:
        The TimeSeries with infilling and infill flags applied.
    """
    # Currently only have config info in the metadata API for CHIMN.  Hack it here so other sites use this for now...
    # TODO: REMOVE THIS WHEN WE HAVE ALL CONFIGS IN THE API
    INFILL_CONFIGS[site_id] = INFILL_CONFIGS["CHIMN"]

    # Filter configs by the site and resolution
    infill_configs = INFILL_CONFIGS.get(site_id, {}).get(ts.resolution.iso_duration)

    if not infill_configs:
        logger.info(f"No infilling configs found for site: {site_id}")
        return ts

    # Initialise infilling flag system within TimeSeries object
    infill_flags_dict = {method: method_config.method_id for method, method_config in INFILL_METHODS.items()}
    if infill_flags_dict:
        ts.add_flag_system(INFILL_FLAG_SYS_NAME, infill_flags_dict)
    else:
        logger.warning("No infill methods given in config.")
        return ts

    for column in ts.data_columns:
        methods = infill_configs.get(column)
        if methods:
            # Order by priority
            sorted_methods = sorted(methods, key=lambda x: x.priority)
            for method_config in sorted_methods:
                infill_flag_col = infill_flag_column_name(column)

                if infill_flag_col not in ts.flag_columns:
                    ts.init_flag_column(INFILL_FLAG_SYS_NAME, infill_flag_col)

                # Run infill function
                infill_func = INFILL_METHODS[method_config.method.name]
                logger.info(
                    f"Infilling {column} with method: {method_config.method.name}. "
                    f"Constraints: {method_config.method.parameters}"
                )
                ts = infill_func(ts, column, infill_flag_col, **method_config.method.parameters)

        else:
            logger.warning(f"No infill methods for: {column}")

    return ts
