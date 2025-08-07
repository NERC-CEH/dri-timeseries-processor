import logging
from datetime import datetime
from functools import lru_cache
from typing import Dict

import polars as pl

from dritimeseriesprocessor.dri_typing import TimeseriesContainerWithDerivations
from dritimeseriesprocessor.flagging.flagger import corrs_flag_column_name, update_corrections_core_flags
from dritimeseriesprocessor.metrics_exporter import metrics
from dritimeseriesprocessor.utils import not_missing_expr
from metadata_manager.models.service import load_config, load_methods

logger = logging.getLogger(__name__)

CORRS_FLAG_SYS_NAME = "corrs_flags"


@lru_cache(maxsize=1)
def get_correction_methods() -> Dict:
    """Load the correction methods and cache the results."""
    return load_methods("correction")


@metrics.track_corrections_time()
def run_corrections(
    ts_ids: Dict[str, TimeseriesContainerWithDerivations],
) -> Dict[str, TimeseriesContainerWithDerivations]:
    """Corrects the data by applying a series of corrections based on predefined configurations.

    Args:
        ts_ids: Metadata and data for timeseries ids

    Returns:
        ts_ids: Metadata and corrected data for timeseries ids
    """
    correction_methods = get_correction_methods()

    # Initialise corrections flag system within TimeSeries object
    correction_flags_dict = {method: method_config.method_id for method, method_config in correction_methods.items()}
    if not correction_flags_dict:
        logger.warning("No QC methods given in config.")
        return ts_ids

    for ts_id, ts_dict in ts_ids.items():
        ts = ts_dict["data"]

        correction_config = load_config("correction", ts_id)
        if not correction_config:
            logger.info(f"No correction config found for Time Series ID: {ts_id}")
            continue

        # Initialise correction flag system within TimeSeries object.
        if CORRS_FLAG_SYS_NAME not in ts.flag_systems:
            ts.add_flag_system(CORRS_FLAG_SYS_NAME, correction_flags_dict)

        # Add a flag column for the correction method
        corrs_flag_col = corrs_flag_column_name(ts.column_name)
        if corrs_flag_col not in ts.columns:
            ts.init_flag_column(CORRS_FLAG_SYS_NAME, corrs_flag_col)

        for config in correction_config:
            # Run the corrections on the timeseries
            for method in config.configs:
                # Ensure the end datetime is set; default to the current time if not provided
                if method.observation_interval[1] is None:
                    method.observation_interval = (method.observation_interval[0], datetime.now())

                logger.info(
                    f"Applying correction for {ts_id}: {method.name} between "
                    f"{method.observation_interval[0].strftime('%Y-%m-%d %H:%M:%S')} and "
                    f"{method.observation_interval[1].strftime('%Y-%m-%d %H:%M:%S')}"
                )

                # Create a mask to filter rows based on SITE_ID and the time range
                mask = (pl.col(ts.time_name) >= method.observation_interval[0]) & (
                    pl.col(ts.time_name) <= method.observation_interval[1]
                )

                # Apply the specified correction function to the DataFrame
                correction_function = correction_methods[method.name]
                ts.df = correction_function(ts.df, ts.column_name, method.parameters["correction_factor"], mask)

                # Apply flagging to the DataFrame.
                expr = mask & not_missing_expr(ts.column_name)
                ts.add_flag(corrs_flag_col, method.name, expr)

        ts = update_corrections_core_flags(ts)

    return ts_ids
