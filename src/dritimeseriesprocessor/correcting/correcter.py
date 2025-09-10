import logging
from functools import lru_cache
from typing import Dict

import polars as pl
from time_stream.utils import get_date_filter

from dritimeseriesprocessor.correcting.operations import Operation
from dritimeseriesprocessor.flagging.flagger import corrs_flag_column_name, update_corrections_core_flags
from dritimeseriesprocessor.local_typing import TimeseriesContainer
from dritimeseriesprocessor.metrics_exporter import metrics
from dritimeseriesprocessor.utils import extract_dep_ts, not_missing_expr
from metadata_manager.models.common import build_processing_config_timeseries_id_query_parameter
from metadata_manager.models.service import load_config, load_methods

logger = logging.getLogger(__name__)

CORRS_FLAG_SYS_NAME = "corrs_flags"


@lru_cache(maxsize=1)
def get_correction_methods() -> Dict:
    """Load the correction methods and cache the results."""
    return load_methods("correction")


@metrics.track_corrections_time()
def run_corrections(
    ts_ids: Dict[str, TimeseriesContainer],
) -> Dict[str, TimeseriesContainer]:
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
        logger.warning("No correction methods given in config.")
        return ts_ids

    for ts_id, ts_dict in ts_ids.items():
        ts = ts_dict["data"]

        ts_id_query_param = build_processing_config_timeseries_id_query_parameter(ts_id)
        correction_configs = load_config("correction", ts_id_query_param)
        if not correction_configs:
            logger.info(f"No correction config found for Time Series ID: {ts_id}")
            continue

        # Initialise correction flag system within TimeSeries object.
        if CORRS_FLAG_SYS_NAME not in ts.flag_systems:
            ts.add_flag_system(CORRS_FLAG_SYS_NAME, correction_flags_dict)

        # Add a flag column for the correction method
        corrs_flag_col = corrs_flag_column_name(ts.column_name)
        if corrs_flag_col not in ts.columns:
            ts.init_flag_column(CORRS_FLAG_SYS_NAME, corrs_flag_col)

        for correction_config in correction_configs:
            # Run the corrections on the timeseries
            for corr_config in correction_config.configs:
                if corr_config.observation_interval:
                    date_filter = get_date_filter(ts.time_name, corr_config.observation_interval)
                else:
                    date_filter = pl.lit(True)

                # Only apply the correction if there is data in the observation interval
                if ts.df.filter(date_filter).is_empty():
                    logger.info(
                        f"No data in observation interval {corr_config.observation_interval} for "
                        f"Time Series ID: {ts_id}, skipping correction {corr_config.name}"
                    )
                    continue

                corr_method_metadata = correction_methods.get(corr_config.name)
                if not corr_method_metadata:
                    raise ValueError(f"Correction method {corr_config.name} not found in methods registry.")

                corr_config_update = extract_dep_ts(corr_config, ts_ids)

                if corr_method_metadata.arg_mapping:
                    # Map argument names to match those expected by the operation, where needed.
                    for old_name, new_name in corr_method_metadata.arg_mapping.items():
                        if old_name in corr_config_update.parameters:
                            corr_config_update.parameters[new_name] = corr_config_update.parameters.pop(old_name)

                # Apply the specified correction function to the DataFrame
                op = Operation.get(corr_method_metadata.function_name, **corr_config_update.parameters)
                ts = op.apply(
                    ts,
                    filter_expr=date_filter,
                )

                # Apply flagging to the DataFrame.
                expr = date_filter & not_missing_expr(ts.column_name)
                ts.add_flag(corrs_flag_col, corr_config_update.name, expr)

        ts = update_corrections_core_flags(ts)

    return ts_ids
