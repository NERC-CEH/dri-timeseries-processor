"""
Helper functions related to Polars DataFrames
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
    if df.is_empty():
        return []
    # group_by returns groups as `[(key_tuple, DataFrame), ...]`
    grouper = df.group_by(pl.col(time_col).dt.date())
    split_dfs = [(group_key[0], group_df) for group_key, group_df in grouper]
    split_dfs.sort(key=lambda x: x[0])
    return split_dfs


def merge_dataframes(df1: pl.DataFrame, df2: pl.DataFrame, join_col: str) -> pl.DataFrame:
    """Merge two aligned Polars DataFrames.

    Args:
        df1: First Polars DataFrame to merge
        df2: Second Polars DataFrame to merge
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
    combined_df = combined_df.select(join_col, *extra_from_df2, *coalesce_cols, *extra_from_df1).sort(join_col)

    return combined_df


def missing_expr(column_name: str) -> pl.Expr:
    """Return expression for missing values in column.

    Args:
        column_name: Data column name

    Returns:
        Expression for missing values
    """
    return pl.col(column_name).is_null() | pl.col(column_name).is_nan()


def not_missing_expr(column_name: str) -> pl.Expr:
    """Return expression for not missing values in column.

    Args:
        column_name: Data column name

    Returns:
        Expression for not missing values
    """
    return pl.col(column_name).is_not_null() & pl.col(column_name).is_not_nan()
