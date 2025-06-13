import logging
from functools import lru_cache
from typing import Dict

import polars as pl
from time_stream import TimeSeries

from dritimeseriesprocessor.flagging.flagger import qc_flag_column_name, update_quality_control_core_flags
from dritimeseriesprocessor.metrics_exporter import metrics
from metadata_manager.models.service import load_config, load_methods

logger = logging.getLogger(__name__)


QC_FLAG_SYS_NAME = "qc_flags"


@lru_cache(maxsize=1)
def get_qc_methods() -> Dict:
    """Load the qc methods and cache the results."""
    return load_methods("quality_control")


def remove_qcd_data(df: pl.DataFrame, column: str, flag_column: str) -> pl.DataFrame:
    """
    Remove values that have a QC flag for given column.

    Args:
        df: Dataframe containing data and QC flag column
        column: Name data column
        flag_column: Name of QC flag column

    Returns:
        pl.DataFrame with QC'd data removed
    """
    # Remove data
    return df.with_columns(pl.when(pl.col(flag_column) > 0).then(None).otherwise(pl.col(column)).alias(column))


@metrics.track_qc_time()
def run_quality_control(
    data_groups: Dict[str, TimeSeries], ts_ids_metadata: Dict[str, Dict[str, str]], remove: bool = False
) -> TimeSeries:
    """Run data through Quality Control (QC) checks.

    Applies a series of quality control checks to the input DataFrame based on
    the configuration specified in the qc_config module.

    Args:
        data_groups: Dictionary containing timeseries data by group id.
        ts_ids_metadata: The metadata for the TimeSeries IDs.
        remove: Whether to remove any QC'd data.

    Returns:
        The TimeSeries with quality control flags applied.
    """
    qc_methods = get_qc_methods()

    # Initialise quality control flag system within TimeSeries object
    qc_flags_dict = {method: method_config.method_id for method, method_config in qc_methods.items()}
    if not qc_flags_dict:
        logger.warning("No QC methods given in config.")
        return data_groups

    for ts_id, ts_metadata in ts_ids_metadata.items():
        group_id = ts_metadata["group_id"]
        # Check there is data availble for this ts_id
        ts = data_groups.get(group_id)
        if ts is None:
            continue

        qc_configs = load_config("quality_control", ts_id)
        if not qc_configs:
            logger.info(f"No quality control config found for Time Series ID: {ts_id}")
            continue

        # Set up the flag system if it doesn't already exist
        if QC_FLAG_SYS_NAME not in ts.flag_systems:
            ts.add_flag_system(QC_FLAG_SYS_NAME, qc_flags_dict)

        column = ts_metadata["sourceColumnName"]
        if not column:
            # TODO: We should not be using the sourceColumnName here as we may be QC-ing a derived column. FPM-403
            logger.warning(f"No source column name provided for TimeSeries ID: {ts_id}")
            continue

        # Check the target variable exists in the TimeSeries DataFrame
        if column not in ts.data_columns:
            logger.warning(f"Variable {column} not in DataFrame for TimeSeries ID: {ts_id}")
            continue

        for config in qc_configs:
            qc_flag_col = qc_flag_column_name(column)
            if qc_flag_col not in ts.flag_columns:
                ts.init_flag_column(QC_FLAG_SYS_NAME, qc_flag_col)

            # Run QC methods on time series
            # TODO: Will have to add in start and end dates so that QC only applied to specific part of time
            #  series that config is valid for, based on observationInterval startDate and endDate - see ticket FW-740
            for method in config.configs:
                qc_func = qc_methods[method.name]
                logger.info(
                    f"Quality controlling {column} with method: {method.name}. Constraints: {method.parameters}"
                )
                ts = qc_func(ts, column, qc_flag_col, method.name, **method.parameters)

                if remove:
                    ts.df = remove_qcd_data(ts.df, column, qc_flag_col)

    for group_id, ts in data_groups.items():
        data_groups[group_id] = update_quality_control_core_flags(ts)
        logger.info(f"Ran quality control successfully for {group_id}. Shape: {ts.df.shape}")

        qcflag_columns = [col for col in ts.columns if col.endswith("_QCFLAG")]
        flags_count = len(qcflag_columns)
        logger.info(f"Number of QC flag columns: {flags_count}")
        metrics.increment_flags(flags_count)

    return data_groups
