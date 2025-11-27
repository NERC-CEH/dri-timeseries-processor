"""
Helper functions related to DataFrames
"""

from datetime import datetime

import polars as pl


def split_by_date(df: pl.DataFrame, time_col: str) -> list[tuple[datetime, pl.DataFrame]]:
    """Split a Polars DataFrame into daily partitions based on the time column.

    Args:
        df: The dataframe to split
        time_col: The name of the time column

    Returns:
        A list of `(date, dataframe)` tuples, where each DataFrame contains only rows belonging to a single date.
    """
    # group_by returns groups as `[(key_tuple, DataFrame), ...]`
    grouper = df.group_by(pl.col(time_col).dt.date())
    return [(group_key[0], group_df) for group_key, group_df in grouper]


def merge_dataframes(df1: pl.DataFrame, df2: pl.DataFrame, join_col: str) -> pl.DataFrame:
    """Merge two aligned Polars DataFrames.

    Args:
        df1: First Polars DataFrame to merge
        df2: Second Polars DataFrame to merge
        join_col: The column to join on

    Returns:
        A merged DataFrame containing all relevant columns.
    """
    common_cols = set(df1.columns) & set(df2.columns)
    update_cols = {c for c in common_cols if c != join_col}

    extra_from_df1 = set(df1.columns) - common_cols
    extra_from_df2 = set(df2.columns) - common_cols

    # Outer join with suffixing for new_df
    combined_df = df1.join(
        df2,
        on=join_col,
        how="full",
        suffix="_current",
        coalesce=True,
    )

    # Build final set of columns
    coalesce_cols = [pl.coalesce(f"{col}_current", col).alias(col) for col in update_cols]
    combined_df = combined_df.select(join_col, *extra_from_df2, *coalesce_cols, *extra_from_df1)

    return combined_df
