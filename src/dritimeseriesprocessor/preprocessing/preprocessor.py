import logging
from datetime import datetime

import polars as pl
import pytz

from dritimeseriesprocessor.__metadata__.config_preprocessing import preprocessing_config
from dritimeseriesprocessor.metrics_exporter import metrics
from dritimeseriesprocessor.preprocessing.operations import CORRECTION_METHODS
from time_series import TimeSeries

logger = logging.getLogger(__name__)


PR_FLAG_SYS_NAME = "pr_flags"


def pr_flag_column_name(column: str) -> str:
    """Return column name of preprocess flag column for a given variable column."""
    return f"{column}_PRFLAG"


@metrics.track_preprocessing_time()
def run_preprocess(ts: TimeSeries) -> TimeSeries:
    """Preprocesses the DataFrame by applying a series of corrections based on predefined configurations.

    Args:
        ts: The input TimeSeries that needs preprocessing.

    Returns:
        The preprocessed DataFrame with corrections applied.
    """
    # Initialise preprocessing flag system within TimeSeries object
    pr_flags_dict = {method.method_id: method.id for method in preprocessing_config.correction_methods}
    if pr_flags_dict:
        ts.add_flag_system(PR_FLAG_SYS_NAME, pr_flags_dict)
    else:
        logger.warning("No correction methods given in config.")
        return ts

    for correction_config in preprocessing_config.corrections:
        # Check the target variable exists in the TimeSeries DataFrame
        if correction_config.variable not in ts.data_columns:
            logger.warning(
                f"Variable {correction_config.variable} not in DataFrame for method {correction_config.method_id}"
            )
            continue

        # If variable exists, add a flag column for the correction method
        pr_flag_col = pr_flag_column_name(correction_config.variable)
        if pr_flag_col not in ts.columns:
            ts.init_flag_column(PR_FLAG_SYS_NAME, pr_flag_col)

        # Check if the correction method is implemented
        correction_fn = CORRECTION_METHODS.get(correction_config.method_id)
        if not correction_fn:
            logger.warning(f"Unimplemented method: {correction_config.method_id}")
            continue

        # Ensure the end datetime is set; default to the current time if not provided
        if correction_config.end_datetime is None:
            correction_config.end_datetime = datetime.now()

        # Create a mask to filter rows based on SITE_ID and the time range
        mask = (
            (pl.col("SITE_ID") == correction_config.site_id)
            & (pl.col(ts.time_name) >= correction_config.start_datetime.replace(tzinfo=pytz.UTC))
            & (pl.col(ts.time_name) <= correction_config.end_datetime.replace(tzinfo=pytz.UTC))
        )

        # Apply the specified correction function to the DataFrame
        ts.df = correction_fn(ts.df, correction_config.variable, correction_config.correction_factor, mask)

        # Apply flagging to the DataFrame.
        expr = mask & pl.col(correction_config.variable).is_not_null()
        ts.add_flag(pr_flag_col, correction_config.method_id, expr)

    return ts
