import logging
from datetime import datetime

import polars as pl
import pytz

from dritimeseriesprocessor.__metadata__.config_preprocessing import preprocessing_config
from dritimeseriesprocessor.metrics_exporter import metrics
from dritimeseriesprocessor.preprocessing.operations import preprocessing_corrections
from time_series import TimeSeries

logger = logging.getLogger(__name__)


def pr_flag_column_name(column: str) -> str:
    """Return column name of preprocess flag column for a given variable column."""
    return f"{column}_PRFLAG"


def initialise_preprocessing_column(ts: TimeSeries, pr_flag_column: str) -> tuple[TimeSeries, str]:
    """Initialise a preprocessing flag column in the DataFrame if it doesn't already exist.

    Args:
        ts: The TimeSeries to operate on.
        pr_flag_column: The name of the preprocessing flag column that should be checked/created.

    Returns:
        A tuple containing the updated DataFrame and the name of the QC flag column.
    """
    if pr_flag_column not in ts.df.columns:
        ts.df = ts.df.with_columns(pl.lit(None, dtype=pl.UInt64).alias(pr_flag_column))
        ts.set_supplementary_columns(pr_flag_column)

    return ts


@metrics.track_preprocessing_time()
def run_preprocess(ts: TimeSeries) -> TimeSeries:
    """Preprocesses the DataFrame by applying a series of corrections based on predefined configurations.

    Args:
        ts: The input TimeSeries that needs preprocessing.

    Returns:
        The preprocessed DataFrame with corrections applied.
    """
    for correction_config in preprocessing_config.corrections:
        # Check if the correction method is implemented
        correction_fn = preprocessing_corrections.get(correction_config.METHOD_ID)
        if not correction_fn:
            logger.warning(f"Unimplemented method: {correction_config.METHOD_ID}")
            continue

        # Check if the target variable exists in the DataFrame
        if correction_config.VARIABLE not in ts.df:
            logger.warning(
                f"Variable {correction_config.VARIABLE} not in DataFrame for method {correction_config.METHOD_ID}"
            )
            continue

        # Ensure the end datetime is set; default to the current time if not provided
        if correction_config.END_DATETIME is None:
            correction_config.END_DATETIME = datetime.now()

        # Create a mask to filter rows based on SITE_ID and the time range
        mask = (
            (pl.col("SITE_ID") == correction_config.SITE_ID)
            & (pl.col("time") >= correction_config.START_DATETIME.replace(tzinfo=pytz.UTC))
            & (pl.col("time") <= correction_config.END_DATETIME.replace(tzinfo=pytz.UTC))
        )

        # Apply the specified correction function to the DataFrame
        pr_flag_col = pr_flag_column_name(correction_config.VARIABLE)
        ts = initialise_preprocessing_column(ts, pr_flag_col)
        ts.df = correction_fn(ts.df, correction_config, pr_flag_col, mask)

    return ts
