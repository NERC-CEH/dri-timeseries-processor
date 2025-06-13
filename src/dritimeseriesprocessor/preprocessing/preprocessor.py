import logging
from datetime import datetime
from typing import Dict

import polars as pl
import pytz
from time_stream import TimeSeries

from dritimeseriesprocessor.__metadata__.config_preprocessing import preprocessing_config
from dritimeseriesprocessor.flagging.flagger import pr_flag_column_name, update_preprocess_core_flags
from dritimeseriesprocessor.metrics_exporter import metrics
from dritimeseriesprocessor.preprocessing.operations import CORRECTION_METHODS
from dritimeseriesprocessor.utils import not_missing_expr

logger = logging.getLogger(__name__)


PR_FLAG_SYS_NAME = "pr_flags"


@metrics.track_preprocessing_time()
def run_preprocess(data_groups: Dict[str, TimeSeries]) -> Dict[str, TimeSeries]:
    """Preprocesses the data by applying a series of corrections based on predefined configurations.

    Args:
        data_groups: Dictionary containing timeseries data by group id.

    Returns:
        data_groups: Dictionary of timeseries objects with corrected data.
    """
    pr_flags_dict = {method.method_id: method.id for method in preprocessing_config.correction_methods}
    if not pr_flags_dict:
        logger.warning("No correction methods given in config.")
        return data_groups

    for group_id, ts in data_groups.items():
        # Initialise preprocessing flag system within TimeSeries object.
        ts.add_flag_system(PR_FLAG_SYS_NAME, pr_flags_dict)

        for correction_config in preprocessing_config.corrections:
            if correction_config.site_id != ts.site_id:
                continue

            # Check the target variable exists in the TimeSeries DataFrame
            if correction_config.variable not in ts.data_columns:
                logger.warning(
                    f"Variable {correction_config.variable} not in DataFrame for method {correction_config.method_id}"
                )
                continue

            # Check if the correction method is implemented
            correction_fn = CORRECTION_METHODS.get(correction_config.method_id)
            if not correction_fn:
                logger.warning(f"Unimplemented method: {correction_config.method_id}")
                continue

            # If variable exists, add a flag column for the correction method
            pr_flag_col = pr_flag_column_name(correction_config.variable)
            if pr_flag_col not in ts.columns:
                ts.init_flag_column(PR_FLAG_SYS_NAME, pr_flag_col)

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
            expr = mask & not_missing_expr(correction_config.variable)
            ts.add_flag(pr_flag_col, correction_config.method_id, expr)

        data_groups[group_id] = update_preprocess_core_flags(ts)
        logger.info(f"Ran preprocessor successfully for {group_id}. Shape: {ts.df.shape}")

    return data_groups
