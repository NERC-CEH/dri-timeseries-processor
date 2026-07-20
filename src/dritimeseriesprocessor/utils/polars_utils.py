"""
Helper functions related to Polars DataFrames
"""

from collections.abc import Sequence
from datetime import datetime

import polars as pl

# Deprecation warning from Polars:
#   DeprecationWarning: the `polars.type_aliases` module was deprecated in version 1.0.0. The type aliases have moved
#   to the `polars._typing` module to explicitly mark them as private. Please define your own type aliases, or
#   temporarily import from the `polars._typing` module. A public `polars.typing` module will be added in the future.
# noinspection PyProtectedMember
from polars._typing import JoinStrategy


def split_by_date(df: pl.DataFrame, time_col: str) -> list[tuple[datetime, pl.DataFrame]]:
    """Split a Polars DataFrame into daily partitions based on the time column.

    Args:
        df: The dataframe to split
        time_col: The name of the time column

    Returns:
        A list of `(date, dataframe)` tuples, where each DataFrame contains only rows belonging to a single date.
    """
    if df.is_empty():
        return []
    # group_by returns groups as `[(key_tuple, DataFrame), ...]`
    grouper = df.group_by(pl.col(time_col).dt.date())
    split_dfs = [(group_key[0], group_df) for group_key, group_df in grouper]
    split_dfs.sort(key=lambda x: x[0])
    return split_dfs


def merge_dataframes(df1: pl.DataFrame, df2: pl.DataFrame, join_col: str) -> pl.DataFrame:
    """Merge two aligned Polars DataFrames, with the second taking precedence.

    Where a row appears in both, df2 decides the value of every column it holds, including where that value is
    null - this lets a re-run remove a value it has decided is bad, and keeps a flag column in step with the data
    column it describes. Columns that only df1 holds are kept as they are. Rows that only df1 holds are kept too.

    Args:
        df1: First Polars DataFrame to merge
        df2: Second Polars DataFrame to merge, taking precedence over the first
        join_col: The column to join on

    Returns:
        A merged DataFrame containing all relevant columns.
    """
    if df1.is_empty() and df2.is_empty():
        return pl.DataFrame()

    if df1.is_empty() and not df2.is_empty():
        return df2

    if not df1.is_empty() and df2.is_empty():
        return df1

    if join_col not in df1.columns or join_col not in df1.columns:
        raise ValueError(f"join_col '{join_col}' must exist in both DataFrames.")

    common_cols = set(df1.columns) & set(df2.columns)
    update_cols = {c for c in common_cols if c != join_col}

    extra_from_df1 = set(df1.columns) - common_cols
    extra_from_df2 = set(df2.columns) - common_cols

    # A marker column that is only non-null for rows that came from df2, so it can be distinguished from a column
    # that is null because df2 explicitly holds a null for that row.
    from_df2_marker = "__from_df2__"
    df2 = df2.with_columns(pl.lit(True).alias(from_df2_marker))

    # the suffix applies to the right frame's colliding columns, so join df1 as the right frame and tag as "_previous".
    combined_df = df2.join(
        df1,
        on=join_col,
        how="full",
        suffix="_previous",
        coalesce=True,
    )

    # For columns present in both, take df2's value wherever df2 has a row for that join key (even if that value
    # is null), and only fall back to df1's value for rows that only exist in df1.
    update_exprs = [
        pl.when(pl.col(from_df2_marker)).then(pl.col(col)).otherwise(pl.col(f"{col}_previous")).alias(col)
        for col in update_cols
    ]
    combined_df = combined_df.select(join_col, *extra_from_df2, *update_exprs, *extra_from_df1).sort(join_col)

    return combined_df


def missing_expr(column_name: str, dtype: pl.DataType) -> pl.Expr:
    """Return expression for missing values in column.

    Args:
        column_name: Data column name
        dtype: Data type

    Returns:
        Expression for missing values
    """
    col = pl.col(column_name)
    if dtype.is_float():
        return col.is_null() | col.is_nan()
    else:
        # booleans, ints, strings cannot contain NaN
        return col.is_null()


def not_missing_expr(column_name: str, dtype: pl.DataType) -> pl.Expr:
    """Return expression for not missing values in column.

    Args:
        column_name: Data column name
        dtype: Data type

    Returns:
        Expression for not missing values
    """
    col = pl.col(column_name)
    if dtype.is_float():
        return col.is_not_null() & col.is_not_nan()
    else:
        return col.is_not_null()


def merge_multiple(inputs: list[pl.DataFrame], join_col: str, join_type: JoinStrategy = "full") -> pl.DataFrame:
    """Merge multiple Polars DataFrames on a common column.

    Args:
        inputs: List of DataFrames to merge. Each must contain `join_col`.
        join_col: Name of the column to join on.
        join_type: Type of join to use
    """
    # Use the first dataframe as base
    merged = inputs[0]

    # Sequentially join all remaining dataframes
    for other in inputs[1:]:
        merged = merged.join(other, on=join_col, how=join_type, coalesce=True)

    return merged


def join_time_intervals(
    intervals: Sequence[tuple[datetime, datetime | None, float]],
    df: pl.DataFrame,
    time_name: str,
    value_name: str,
) -> pl.DataFrame:
    """Join time-varying interval values onto a DataFrame using an as-of interval lookup.

    Each interval is defined by a (start, end, value) tuple, where:
      - start is inclusive
      - end is exclusive (or open-ended if None)

    For each row in the DataFrame, the function finds the most recent interval whose start time is less than or
    equal to the row's time, and whose end time (if present) is greater than the row's time. Uses the Polars
    `join_asof` with a backward strategy.

    Args:
        intervals: List of (start, end, value) tuples defining the intervals. end=None indicates an open-ended interval.
        df: Input DataFrame to join to
        time_name: Name of time column in the DataFrame
        value_name: Name of value column in the interval tuples

    Returns:
        A new DataFrame with all original columns preserved, plus an additional column named `value_name` containing
        the matched interval value (or null if no interval applies).
    """
    intervals_df = pl.DataFrame(
        intervals, orient="row", schema={"start": pl.Datetime, "end": pl.Datetime, value_name: pl.Float64}
    ).sort("start")

    # Validate that ends always after starts
    invalid_lengths = intervals_df.filter(pl.col("end").is_not_null() & (pl.col("end") <= pl.col("start")))
    if invalid_lengths.height > 0:
        raise ValueError(f"Invalid interval(s) detected: 'end' must be greater than 'start': {invalid_lengths}")

    # Validate that no overlaps between intervals
    overlaps = intervals_df.with_columns(next_start=pl.col("start").shift(-1)).filter(
        pl.col("end").is_not_null() & (pl.col("next_start") < pl.col("end"))
    )
    if overlaps.height > 0:
        raise ValueError(f"Overlapping intervals detected: an interval starts before the previous one ends: {overlaps}")

    # Validate there is only one open-ended interval - and is the last one
    n_open = intervals_df.select(pl.col("end").is_null().sum().alias("n_open")).item()
    if n_open > 1:
        raise ValueError(f"Invalid intervals: found {n_open} open-ended intervals (end=None); expected at most 1.")
    if (
        intervals_df.with_row_index()
        .filter(pl.col("end").is_null() & (pl.col("index") < intervals_df.height - 1))
        .height
        > 0
    ):
        raise ValueError("Open-ended interval must be the last interval.")

    # Perform the ASOF join that matches the nearest previous value from the intervals
    joined = df.join_asof(intervals_df, left_on=time_name, right_on="start", strategy="backward")

    # Ensure that any rows that fall between intervals are given a None value
    joined = joined.with_columns(
        pl.when(pl.col("end").is_null() | (pl.col(time_name) < pl.col("end"))).then(pl.col(value_name)).otherwise(None)
    ).drop(["start", "end"])

    return joined
