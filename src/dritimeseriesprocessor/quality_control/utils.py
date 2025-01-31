import logging
from typing import List, Union

import polars as pl

from dritimeseriesprocessor.__metadata__.config_quality_control import get_qc_config
from time_series import TimeSeries

logger = logging.getLogger(__name__)


def column_threshold_check(
    ts: TimeSeries,
    check_column: str,
    flag_column: str,
    threshold: float,
    operator: str,
    flag_id: Union[int, str],
    flag_na: bool = False,
) -> TimeSeries:
    """Generic function for flagging one column of data, based on a threshold check of a different column

    For example, we could look at the battery voltage column (the "check_column"), compare it to a threshold
    using the given operator (e.g. which rows are < threshold), then the "flag_column" for any rows that are True for
    this check are flagged

    Args:
        ts: TimeSeries object containing the data to be checked.
        check_column: The column of data that is being checked against the threshold
        flag_column: The column to which flag value should be added
        threshold: Threshold value
        operator: What comparison to make
        flag_id: The integer ID or the flag name, of the quality control flag that should be applied to data that
            fail this check.
        flag_na: Comparison tests against NaNs will always result in False. By default, NaN values will not cause
            data in data to be flagged. Set this to True to change that.

    Returns:
        DataFrame with flags applied to qc_column.
    """

    operator_map = {
        ">": pl.col(check_column).gt(threshold),
        ">=": pl.col(check_column).ge(threshold),
        "<": pl.col(check_column).lt(threshold),
        "<=": pl.col(check_column).le(threshold),
        "==": pl.col(check_column).eq(threshold),
        "!=": pl.col(check_column).ne(threshold),
    }

    if check_column not in ts.columns:
        raise UserWarning(f"Can not run column threshold check. No {check_column} data provided")

    if flag_column not in ts.columns:
        raise UserWarning(f"Can not run column threshold check. No {flag_column} flag column in dataframe")

    if operator not in operator_map:
        raise ValueError(f"{operator} is an invalid operator, use: {', '.join(operator_map.keys())}")

    # Get the operator expression
    operator_expr = operator_map[operator]
    if flag_na:
        operator_expr = operator_expr | pl.col(check_column).is_null()

    # Apply the flags based on comparing requested column to the threshold
    ts.add_flag(flag_column, flag_id, operator_expr)

    return ts


def get_site_spike_threshold(site_id: str, variable: str, resolution: str) -> float:
    """Get the site-specific spike threshold values for a given site, column and resolution.

    Args:
        site_id: Site ID for which spike threshold is needed
        variable: The variable name for which spike threshold is needed
        resolution: The temporal resolution for which spike threshold is needed

    Returns:
        Spike threshold
    """
    spike_thresholds = get_qc_config("spike_thresholds")
    spike_threshold = spike_thresholds.get(variable)
    if spike_threshold is None:
        raise UserWarning(f"No {variable} spike thresholds provided.")

    # Get the default values for the given resolution
    default_spike_threshold_value = next(
        (
            spike_thresh
            for spike_thresh in spike_threshold.defaults
            if spike_thresh.resolutions is None or resolution in spike_thresh.resolutions
        ),
        None,
    )

    # Get the site specific values for the given site and resolution, defaulting to default values if not found
    if spike_threshold.sites:
        spike_threshold_value = next(
            (
                spike_thresh
                for spike_thresh in spike_threshold.sites
                if spike_thresh.site_id == site_id
                and (spike_thresh.resolutions is None or resolution in spike_thresh.resolutions)
            ),
            default_spike_threshold_value,
        )
    else:
        spike_threshold_value = default_spike_threshold_value

    if spike_threshold_value is None:
        raise ValueError(f"No spike threshold set for {variable} spike test")

    return spike_threshold_value.threshold


def get_site_range_values(site_id: str, variable: str, resolution: str) -> tuple[float, float]:
    """Get the site-specific minimum and maximum values for range check for a given site, column and resolution.

    This function searches through the site-specific range thresholds and returns the min and max values for
    a given site and resolution. If no specific values are found, it returns the default values for that column
    and resolution.

    Args:
        site_id: Site ID for which range values are needed
        variable: The variable name for which range values are needed
        resolution: The temporal resolution for which range values are needed

    Returns:
        A tuple containing the minimum and maximum values for the range check.
    """
    range_thresholds = get_qc_config("range_thresholds")
    range_threshold = range_thresholds.get(variable)
    if range_threshold is None:
        raise UserWarning(f"No {variable} range thresholds provided.")

    # Get the default values for the given resolution
    default_range_values = next(
        (
            range_thresh
            for range_thresh in range_threshold.defaults
            if range_thresh.resolutions is None or resolution in range_thresh.resolutions
        ),
        None,
    )

    # Get the site specific values for the given site and resolution, defaulting to default values if not found
    if range_threshold.sites:
        range_values = next(
            (
                range_thresh
                for range_thresh in range_threshold.sites
                if range_thresh.site_id == site_id
                and (range_thresh.resolutions is None or resolution in range_thresh.resolutions)
            ),
            default_range_values,
        )
    else:
        range_values = default_range_values

    if range_values is None:
        raise ValueError(f"No min/max values set for {variable} range test")

    return range_values.min_value, range_values.max_value


def get_failed_qc_check_ids_from_flag(flag: int) -> List[int]:
    """Returns the indexes of failed tests from a QC flag

    Args:
        flag: The flag to calculate from.

    Returns: A list of indexes to failed QC checks.
    """

    return [1 << i for i, x in enumerate(reversed(bin(flag)[2:])) if x == "1"]
