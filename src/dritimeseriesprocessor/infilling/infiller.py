import logging
from functools import lru_cache
from typing import Dict

from dritimeseriesprocessor.flagging.flagger import infill_flag_column_name, update_infill_core_flags
from dritimeseriesprocessor.typing import TimeseriesContainerWithDerivations
from metadata_manager.models.service import load_config, load_methods

logger = logging.getLogger(__name__)


INFILL_FLAG_SYS_NAME = "infill_flags"


@lru_cache(maxsize=1)
def get_infill_methods() -> Dict:
    """Load the infill methods and cache the results."""
    return load_methods("infilling")


def run_infilling(
    ts_ids: Dict[str, TimeseriesContainerWithDerivations],
) -> Dict[str, TimeseriesContainerWithDerivations]:
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

        # Add a flag column for the infill method
        infill_flag_col = infill_flag_column_name(ts.column_name)
        if infill_flag_col not in ts.flag_columns:
            ts.init_flag_column(INFILL_FLAG_SYS_NAME, infill_flag_col)

        # Order by priority
        sorted_infillers = sorted(infill_configs, key=lambda x: x.annotations["data-processing-configuration-priority"])
        for config in sorted_infillers:
            # Run infill methods on time series
            for infill_method in config.configs:
                method_metadata = infill_methods[infill_method.name]

                # TODO: Unsure whether this parameter is actually needed.  Not used in any method currently.
                infill_method.parameters.pop("window")

                logger.info(
                    f"Infilling {ts.column_name} with method: {infill_method.name}. "
                    f"Constraints: {infill_method.parameters}"
                )

                # To work out which values were infilled
                null_mask_before = ts.df[ts.column_name].is_null()

                # Do the infilling
                ts = ts.infill(
                    method_metadata.function_name,
                    ts.column_name,
                    observation_interval=infill_method.observation_interval,
                    **infill_method.parameters,
                )

                # Update the flag column with the infill method ID
                null_mask_after = ts.df[ts.column_name].is_null()
                #   The values to flag (i.e., the ones that have been infilled) are the ones that were null before
                #       but aren't now
                ts.add_flag(infill_flag_col, infill_method.name, null_mask_before.ne(null_mask_after))

        ts = update_infill_core_flags(ts)

    return ts_ids
