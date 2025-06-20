import logging
from typing import List, Union

import polars as pl
from time_stream import TimeSeries

logger = logging.getLogger(__name__)


def column_threshold_check(
    ts: TimeSeries,
    check_ts: TimeSeries,
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
        ts: TimeSeries object containing the data to be flagged.
        check_ts: TimeSeries object that is being checked against the threshold
        flag_column: The column in ts to which flag value should be added
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
        ">": pl.col(check_ts.column_name).gt(threshold),
        ">=": pl.col(check_ts.column_name).ge(threshold),
        "<": pl.col(check_ts.column_name).lt(threshold),
        "<=": pl.col(check_ts.column_name).le(threshold),
        "==": pl.col(check_ts.column_name).eq(threshold),
        "!=": pl.col(check_ts.column_name).ne(threshold),
    }

    if flag_column not in ts.columns:
        raise UserWarning(f"Can not run column threshold check. No {flag_column} flag column in dataframe")

    if operator not in operator_map:
        raise ValueError(f"{operator} is an invalid operator, use: {', '.join(operator_map.keys())}")

    # Get the operator expression
    operator_expr = operator_map[operator]
    if flag_na:
        operator_expr = operator_expr | pl.col(check_ts.column_name).is_null()

    # Apply the flags based on comparing requested column to the threshold
    ts.add_flag(flag_column, flag_id, check_ts.df.select(operator_expr))

    return ts


def get_failed_qc_check_ids_from_flag(flag: int) -> List[int]:
    """Returns the indexes of failed tests from a QC flag

    Args:
        flag: The flag to calculate from.

    Returns: A list of indexes to failed QC checks.
    """

    return [1 << i for i, x in enumerate(reversed(bin(flag)[2:])) if x == "1"]
