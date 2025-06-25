import logging
from functools import lru_cache
from typing import Dict, Union

from time_stream import TimeSeries

from dritimeseriesprocessor.flagging.flagger import infill_flag_column_name, update_infill_core_flags
from metadata_manager.models.service import load_config, load_methods

logger = logging.getLogger(__name__)


INFILL_FLAG_SYS_NAME = "infill_flags"


@lru_cache(maxsize=1)
def get_infill_methods() -> Dict:
    """Load the infill methods and cache the results."""
    return load_methods("infilling")


def run_infilling(ts_ids: Dict[str, Dict[str, Union[str, TimeSeries]]]) -> Dict[str, Dict[str, Union[str, TimeSeries]]]:
    """Run data through Infilling.

    Reads and applies infill methods for each variable from config.

    Args:
        ts_ids: Metadata and data for timeseries ids

    Returns:
        ts_ids: Metadata and infilled data for timeseries ids
    """
    infill_methods = get_infill_methods()

    # Initialise infilling flag system within TimeSeries object
    infill_flags_dict = {method: method_config.method_id for method, method_config in infill_methods.items()}
    if not infill_flags_dict:
        logger.warning("No infill methods given in config.")
        return ts_ids

    for ts_id, ts_dict in ts_ids.items():
        ts = ts_dict["data"]

        infill_configs = load_config("infilling", ts_id)
        if not infill_configs:
            logger.info(f"No infilling config found for Time Series ID: {ts_id}")
            continue

        # Set up the flag system if it doesn't already exist
        if INFILL_FLAG_SYS_NAME not in ts.flag_systems:
            ts.add_flag_system(INFILL_FLAG_SYS_NAME, infill_flags_dict)

        column = list(ts.data_columns.keys())[0]

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

        ts = update_infill_core_flags(ts)

    return ts_ids
