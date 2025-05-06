import logging
from functools import lru_cache
from typing import Dict

import polars as pl
from time_stream import TimeSeries

from dritimeseriesprocessor.metrics_exporter import metrics
from metadata_manager.models.service import load_config, load_methods

logger = logging.getLogger(__name__)


QC_FLAG_SYS_NAME = "qc_flags"


@lru_cache(maxsize=1)
def get_qc_methods() -> Dict:
    """Load the qc methods and cache the results."""
    return load_methods("quality_control")


def qc_flag_column_name(column: str) -> str:
    """Return column name of QC flag column for a given variable column."""
    return f"{column}_QC_FLAG"


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
def run_quality_control(ts: TimeSeries, ts_ids: str, metadata: Dict, remove: bool = False) -> TimeSeries:
    """Run data through Quality Control (QC) checks.

    Applies a series of quality control checks to the input DataFrame based on
    the configuration specified in the qc_config module.

    Args:
        ts: The input TimeSeries containing the data to be quality controlled.
        ts_ids: List of the TimeSeries IDs being processed.
        metadata: The metadata for the site being processed.
        remove: Whether to remove any QC'd data.

    Returns:
        The TimeSeries with quality control flags applied.
    """
    qc_methods = get_qc_methods()

    # Initialise quality control flag system within TimeSeries object
    qc_flags_dict = {method: method_config.method_id for method, method_config in qc_methods.items()}
    if qc_flags_dict:
        ts.add_flag_system(QC_FLAG_SYS_NAME, qc_flags_dict)
    else:
        logger.warning("No QC methods given in config.")
        return ts

    for ts_id in ts_ids:
        column = metadata[ts_id]["sourceColumnName"]
        qc_configs = load_config("quality_control", ts_id)
        if not qc_configs:
            logger.info(f"No quality control config found for Time Series ID: {ts_id}")
            return ts

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

    return ts
