"""Util functions for managing flag data"""

import logging

import polars as pl

from dritimeseriesprocessor.__metadata__.config_core_flags import core_flag_config
from time_series import TimeSeries

logger = logging.getLogger(__name__)


def initialise_core_flags(ts: TimeSeries) -> TimeSeries:
    """Add core flag column to each data column in Timeseries object, using the
    data column name and flag name for new column name.

    Initialise all columns with the "unchecked" and "missing" flag.

    Args:
        ts: The input TimeSeries object.

    Returns:
        The TimeSeries with the flag columns added
    """
    for data_col_name in ts.data_col_names:
        flag_col_name = f"{data_col_name}_FLAG"
        ts.add_supp_column(flag_col_name, 0)

        ts._df = add_unchecked_flag(ts.df, flag_col_name)
        ts._df = add_missing_flag(ts.df, data_col_name, flag_col_name)

    return ts


def add_unchecked_flag(df: pl.DataFrame, flag_col_name: str) -> pl.DataFrame:
    """
    Add "unchecked" flag to all values in flag column

    Args:
        df: The dataframe to update
        flag_col_name: Name of flag column

    Returns:
        Updated dataframe

    """
    return df.with_columns((pl.col(flag_col_name) + core_flag_config["unchecked"].id).alias(flag_col_name))


def add_missing_flag(df: pl.DataFrame, data_col_name: str, flag_col_name: str) -> pl.DataFrame:
    """
    Add a flag for missing values in the specified data column.

    Args:
        df: The Polars DataFrame to check and update.
        data_col_name: The name of the column to check for missing values.
        flag_col_name: The name of the flag column to add/update with the flag.

    Returns:
        A DataFrame with the flag column updated for missing values in the specified data column.
    """
    return df.with_columns(
        pl.when(pl.col(data_col_name).is_null() | pl.col(data_col_name).is_nan())
        .then(pl.col(flag_col_name) + core_flag_config["missing"].id)
        .otherwise(pl.col(flag_col_name))
        .alias(flag_col_name)
    )
