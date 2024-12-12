import logging

import polars as pl

from dritimeseriesprocessor.__metadata__.config_quality_control import get_qc_config
from dritimeseriesprocessor.metrics_exporter import metrics
from dritimeseriesprocessor.quality_control.checks import QC_CHECKS
from time_series import TimeSeries

logger = logging.getLogger(__name__)


def qc_flag_column_name(column: str) -> str:
    """Return column name of QC flag column for a given variable column."""
    return f"{column}_QCFLAG"


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
def run_quality_control(ts: TimeSeries, remove: bool = False) -> TimeSeries:
    """Run data through Quality Control (QC) checks.

    Applies a series of quality control checks to the input DataFrame based on
    the configuration specified in the qc_config module.

    Args:
        ts: The input TimeSeries containing the data to be quality controlled.
        remove: Whether to remove any QC'd data.

    Returns:
        The TimeSeries with quality control flags applied.
    """

    qc_check_configs = get_qc_config("qc_tests")

    for check_id, check_config in qc_check_configs.items():
        check_func = QC_CHECKS.get(check_id)
        if check_func is None:
            logger.warning(f"Unimplemented method: {check_id}")
            continue

        for column in check_config.variables:
            if column not in ts.data_columns:
                logger.warning(f"Column {column} not in DataFrame for method {check_id}")
                continue

            qc_flag_col = qc_flag_column_name(column)

            if qc_flag_col not in ts.supplementary_columns:
                ts.init_supplementary_column(qc_flag_col, 0)

            ts.df = check_func(ts.df, column, qc_flag_col, check_config.id)

            if remove:
                ts.df = remove_qcd_data(ts.df, column, qc_flag_col)

    return ts
