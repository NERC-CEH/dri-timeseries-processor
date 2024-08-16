"""Quality control helper functions."""

import logging
from typing import Optional, Tuple

import polars as pl

import dritimeseriesprocessor.__metadata__.config_quality_control as qc_config

logger = logging.getLogger(__name__)


def col_comparison_test(
    data: pl.DataFrame, test_col: pl.Series, threshold: float, flag: int, op: str = ">", flag_na: bool = False
) -> pl.DataFrame:
    """
    Generic test function for when a single column of data has implications
    for other columns in the data.

    For example, we would look at the battery voltage column (the
    test_col), compare it to the threshold using the op (which rows are <
    threshold), then all columns (variables) given in data would get the low
    battery flag.

    Args:
        data: This must have only the columns wanted for flagging
        test_col: The column of data that determines which rows get flagged
        threshold: Threshold value
        flag: The flag value used
        op: What comparison to make, see operator_map.
        flag_na: Comparison tests against NaNs will always result in False.
            So by default, NaN values will not cause data in data to be
            flagged. Set this to True to change that.

    Returns:
        DataFrame with flags applied across all columns.
    """

    # Define the operation map for polars
    operator_map = {
        ">": test_col > threshold,
        ">=": test_col >= threshold,
        "<": test_col < threshold,
        "<=": test_col <= threshold,
        "==": test_col == threshold,
        "!=": test_col != threshold,
    }

    # Get the requested operator
    if op not in operator_map:
        raise ValueError(f"{op} is an invalid operator, use: {', '.join(operator_map.keys())}")

    # Apply the operator to the Series
    flag_col = operator_map[op]

    # Handle NaN cases if flag_na is True
    if flag_na:
        flag_col = flag_col | test_col.is_null()

    # Cast the flag column to integers and replace True (1) with the flag value
    flag_col = flag_col.cast(pl.Int32).replace(1, flag)

    # Apply the same flags to all columns in the given data
    flagged_data = data.with_columns([flag_col.alias(col) for col in data.columns])

    return flagged_data


def get_default_range_vals(
    range_threshold: qc_config.VariableRangeThresholds, resolution: str
) -> Tuple[Optional[float], Optional[float]]:
    """
    Get the default minimum and maximum values for a given resolution.

    This function searches through the default range thresholds and returns
    the min and max values based on the provided resolution. If no specific
    resolution is found, it returns the general default values.

    Args:
        range_threshold: The threshold object containing default values.
        resolution: The resolution for which the default range values are needed.

    Returns:
        Tuple[Optional[float], Optional[float]]:
        A tuple containing the minimum and maximum values. Returns
        (None, None) if no values are found.
    """
    min_val = None
    max_val = None

    # Establish defaults
    for range_thres_def in range_threshold.defaults:
        if range_thres_def.resolutions is None:
            # Default regardless of resolution
            min_val = range_thres_def.min_value
            max_val = range_thres_def.max_value

        elif resolution in range_thres_def.resolutions:
            # Defaults found for specific resolution
            min_val = range_thres_def.min_value
            max_val = range_thres_def.max_value
            break

    return min_val, max_val


def get_site_range_vals(
    range_threshold: qc_config.VariableRangeThresholds, site: str, resolution: str
) -> Tuple[Optional[float], Optional[float]]:
    """
    Get the site-specific minimum and maximum values for a given resolution.

    This function searches through the site-specific range thresholds and returns
    the min and max values for a given site and resolution. If no specific
    values are found, it returns (None, None).

    Args:
        range_threshold: The threshold object containing site-specific values.
        site: The site identifier for which range values are needed.
        resolution: The resolution for which the site-specific range values are needed.

    Returns:
        Tuple[Optional[float], Optional[float]]:
        A tuple containing the minimum and maximum values for the site. Returns
        (None, None) if no values are found.
    """
    min_val = None
    max_val = None

    if range_threshold.sites is not None:
        for range_thres_site in range_threshold.sites:
            if range_thres_site.site_id == site and (
                range_thres_site.resolutions is None or resolution in range_thres_site.resolutions
            ):
                min_val = range_thres_site.min_value
                max_val = range_thres_site.max_value
                break

    return min_val, max_val


def add_qcflag_column(df: pl.DataFrame, flags: pl.DataFrame, col_name: str) -> pl.DataFrame:
    """
    Create QC flag column.

    If a quality control flag column already exists for the specified column, the new
    flags are added to the existing ones. If no quality control flag column
    exists, a new column is appended to the DataFrame.

    Args:
        df: Dataframe to add flags to.
        flags: Flag data.
        col_name: Name of column which was tested.

    Returns:
        DataFrame with qc flag column.
    """
    flag_col_name = f"{col_name}_QCFLAG"
    flags = flags.rename({col_name: flag_col_name})

    if flag_col_name in df:
        # Add flag values onto existing values
        df = df.with_columns(pl.col(flag_col_name) + flags[flag_col_name])
    else:
        # Append new column
        df = df.hstack(flags)

    return df
