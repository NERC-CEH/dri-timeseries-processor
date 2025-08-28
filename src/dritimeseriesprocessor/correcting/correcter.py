import logging
from functools import lru_cache
from typing import Dict

from dritimeseriesprocessor.correcting.operations import Operation
from dritimeseriesprocessor.flagging.flagger import corrs_flag_column_name, update_corrections_core_flags
from dritimeseriesprocessor.local_typing import TimeseriesContainerWithDerivations
from dritimeseriesprocessor.metrics_exporter import metrics
from dritimeseriesprocessor.utils import get_date_filter, not_missing_expr
from metadata_manager.models.common import SERVICE_BASE_URI
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

        correction_configs = load_config("correction", ts_id)
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

        for data_processing_config in correction_configs:
            # Run the corrections on the timeseries
            for corr_config in data_processing_config.configs:
                date_filter = get_date_filter(ts.time_name, corr_config.observation_interval)

                # Only apply the correction if there is data in the observation interval
                if not ts.df.filter(date_filter).height:
                    logger.info(
                        f"No data in observation interval {corr_config.observation_interval} for "
                        f"Time Series ID: {ts_id}, skipping correction {corr_config.name}"
                    )
                    continue

                corr_method_metadata = correction_methods.get(corr_config.name)

                # Map dependency time series IDs to TimeSeries objects
                if "dep_ts" in corr_config.parameters:
                    if isinstance(corr_config.parameters["dep_ts"], str):
                        dep_ts_ids = [corr_config.parameters["dep_ts"]]
                    else:
                        dep_ts_ids = corr_config.parameters["dep_ts"]

                    for dep_ts_id in dep_ts_ids:
                        full_dep_ts_id = f"{SERVICE_BASE_URI}/id/dataset/{dep_ts_id.lower()}"
                        if full_dep_ts_id not in ts_ids:
                            raise ValueError(f"Dependency time series ID {dep_ts_id} not found in provided data.")

                        dep_ts = ts_ids[full_dep_ts_id]["data"]
                        # Add the dependency time series to the parameters
                        corr_config.parameters[dep_ts.column_name.lower()] = dep_ts

                    # No longer need this key in the parameters once we've got the dependency time series
                    corr_config.parameters.pop("dep_ts")

                if corr_method_metadata.arg_mapping:
                    for old_name, new_name in corr_method_metadata.arg_mapping.items():
                        if old_name in corr_config.parameters:
                            corr_config.parameters[new_name] = corr_config.parameters.pop(old_name)

                # Apply the specified correction function to the DataFrame
                op = Operation.get(corr_method_metadata.function_name, **corr_config.parameters)
                ts = op.apply(
                    ts,
                    filter_expr=date_filter,
                )

                # Apply flagging to the DataFrame.
                expr = date_filter & not_missing_expr(ts.column_name)
                ts.add_flag(corrs_flag_col, corr_config.name, expr)

        ts = update_corrections_core_flags(ts)

    return ts_ids
