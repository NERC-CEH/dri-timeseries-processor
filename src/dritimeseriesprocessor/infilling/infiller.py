import logging
from functools import lru_cache
from typing import Dict

from time_stream import TimeSeries

from metadata_manager.models.service import load_config, load_methods

logger = logging.getLogger(__name__)


INFILL_FLAG_SYS_NAME = "infill_flags"


@lru_cache(maxsize=1)
def get_infill_methods() -> Dict:
    """Load the infill methods and cache the results."""
    return load_methods("infilling")


def infill_flag_column_name(column: str) -> str:
    """
    Return column name of infill flag column for a given variable column.

    Args:
        column (str): The name of the original variable column.

    Returns:
        str: The name of the corresponding infill flag column, formatted as '{column}_INFILL_FLAG'.
    """
    return f"{column}_INFILL_FLAG"


def run_infilling(ts: TimeSeries, metadata: Dict[str, Dict[str, str]]) -> TimeSeries:
    """Run data through Infilling.

    Reads and applies infill methods for each variable from config.

    Args:
        ts: The input TimeSeries containing the data to be infilled.
        metadata: The metadata for the TimeSeries IDs.

    Returns:
        The TimeSeries with infilling and infill flags applied.
    """
    infill_methods = get_infill_methods()

    # Initialise infilling flag system within TimeSeries object
    infill_flags_dict = {method: method_config.method_id for method, method_config in infill_methods.items()}
    if infill_flags_dict:
        ts.add_flag_system(INFILL_FLAG_SYS_NAME, infill_flags_dict)
    else:
        logger.warning("No infill methods given in config.")
        return ts

    for ts_id, ts_metadata in metadata.items():
        column = ts_metadata["sourceColumnName"]
        infill_configs = load_config("infilling", ts_id)
        if not infill_configs:
            logger.info(f"No infilling config found for Time Series ID: {ts_id}")
            continue

        # Order by priority
        sorted_infillers = sorted(infill_configs, key=lambda x: x.annotations["data-processing-configuration-priority"])
        for config in sorted_infillers:
            infill_flag_col = infill_flag_column_name(column)
            if infill_flag_col not in ts.flag_columns:
                ts.init_flag_column(INFILL_FLAG_SYS_NAME, infill_flag_col)

            # Run infill methods on time series
            # TODO: Will have to add in start and end dates so that infilling only applied to specific part of time
            #  series that config is valid for, based on observationInterval startDate and endDate - see ticket FW-740
            for method in config.configs:
                infill_func = infill_methods[method.name]
                logger.info(f"Infilling {column} with method: {method.name}. Constraints: {method.parameters}")
                ts = infill_func(ts, column, infill_flag_col, method.name, **method.parameters)

    return ts
