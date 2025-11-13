import logging
from functools import lru_cache
from typing import Dict

import time_stream as ts

from dritimeseriesprocessor.flagging.flagger import infill_flag_column_name, update_infill_core_flags
from dritimeseriesprocessor.timeseries_container import TimeseriesContainer
from metadata_manager.models.service import load_methods

logger = logging.getLogger(__name__)


INFILL_FLAG_SYS_NAME = "infill_flags"


@lru_cache(maxsize=1)
def get_infill_methods() -> Dict:
    """Load the infill methods and cache the results."""
    return load_methods("infilling")


def run_infilling(
    ts_ids: Dict[str, TimeseriesContainer],
) -> Dict[str, TimeseriesContainer]:
    """Run data through Infilling.

    Reads and applies infill methods for each variable from config.

    Args:
        ts_ids: Metadata and data for timeseries ids

    Returns:
        ts_ids: Metadata and infilled data for timeseries ids
    """
    infill_methods = get_infill_methods()

    # Initialise infilling flag system within ts.TimeFrame object
    infill_flags_dict = {method: method_config.method_id for method, method_config in infill_methods.items()}
    if not infill_flags_dict:
        logger.warning("No infill methods given in config.")
        return ts_ids

    for ts_id, ts_container in ts_ids.items():
        tf = ts_container.data

        if not ts_container.infill_configs:
            logger.info(f"No infilling config found for Time Series ID: {ts_id}")
            continue

        # Set up the flag system if it doesn't already exist
        try:
            tf.get_flag_system(INFILL_FLAG_SYS_NAME)
        except ts.exceptions.FlagSystemNotFoundError:
            tf.register_flag_system(INFILL_FLAG_SYS_NAME, infill_flags_dict)

        # Add a flag column for the infill method
        infill_flag_col = infill_flag_column_name(tf.metadata["column_name"])
        if infill_flag_col not in tf.flag_columns:
            tf.init_flag_column(tf.metadata["column_name"], INFILL_FLAG_SYS_NAME, infill_flag_col)

        # Order by priority
        sorted_infillers = sorted(ts_container.infill_configs, key=lambda x: x.annotations["priority"])
        for config in sorted_infillers:
            # Run infill methods on time series
            for infill_method in config.configs:
                method_metadata = infill_methods[infill_method.name]

                # TODO: Unsure whether this parameter is actually needed.  Not used in any method currently.
                infill_method.parameters.pop("window", None)

                logger.info(
                    f"Infilling {tf.metadata['column_name']} with method: {infill_method.name}. "
                    f"Constraints: {infill_method.parameters}"
                )
                # Determine which data frame to use for infilling
                if "dep_ts" in infill_method.parameters:
                    # Check if the dependency time series exists
                    dep_ts = infill_method.parameters["dep_ts"]
                    if dep_ts not in ts_ids:
                        logger.warning(f"Dependency time series {dep_ts} not found in ts_ids.")
                        continue

                    # Setup infill parameters for alternative data infilling
                    infill_method.parameters["alt_df"] = ts_ids[dep_ts].data.df
                    infill_method.parameters["alt_data_column"] = ts_ids[dep_ts].data.metadata["column_name"]
                    infill_method.parameters.pop("dep_ts")

                # To work out which values were infilled
                null_mask_before = tf.df[tf.metadata["column_name"]].is_null()

                # Do the infilling
                tf = tf.infill(
                    method_metadata.function_name,
                    tf.metadata["column_name"],
                    observation_interval=infill_method.observation_interval,
                    **infill_method.parameters,
                )

                # Update the flag column with the infill method ID
                null_mask_after = tf.df[tf.metadata["column_name"]].is_null()
                #   The values to flag (i.e., the ones that have been infilled) are the ones that were null before
                #       but aren't now
                tf.add_flag(infill_flag_col, infill_method.name, null_mask_before.ne(null_mask_after))

        tf = update_infill_core_flags(tf)
        ts_ids[ts_id].data = tf

    return ts_ids
