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
    flag_col_dict = {}
    for data_col_name in ts.data_col_names:
        flag_col_dict[data_col_name] = f"{data_col_name}_FLAG"

    flag_col_names = flag_col_dict.values()

    # Add flag columns to TimeSeries as supplementary columns
    ts = ts.df_operation(add_flag_columns, flag_col_names=flag_col_names)
    ts = ts.set_columns_supplemental(flag_col_names)

    # Add initial flags
    ts = ts.df_operation(add_unchecked_flag, flag_col_names=flag_col_names)
    ts = ts.df_operation(add_missing_flag, flag_col_dict=flag_col_dict)

    return ts


def add_flag_columns(df: pl.DataFrame, flag_col_names: list) -> pl.DataFrame:
    """
    Add flag columns to dataframe for each given column, initialising as 0.

    Args:
        df: The dataframe to update
        flag_col_name: Name of flag column

    Returns:
        Updated dataframe
    """
    for flag_col_name in flag_col_names:
        if flag_col_name not in df.columns:
            df = df.with_columns(pl.lit(0).alias(flag_col_name))
    return df


def add_unchecked_flag(df: pl.DataFrame, flag_col_names: list) -> pl.DataFrame:
    """
    Add "unchecked" flag to all values in flag column

    Args:
        df: The dataframe to update
        flag_col_name: Name of flag column

    Returns:
        Updated dataframe
    """
    flag_val = core_flag_config["unchecked"].id

    for flag_col_name in flag_col_names:
        df = df.with_columns((pl.col(flag_col_name) + flag_val).alias(flag_col_name))
    return df


def add_missing_flag(df: pl.DataFrame, flag_col_dict: dict) -> pl.DataFrame:
    """
    Add a flag for missing values in the specified data column.

    Args:
        df: The Polars DataFrame to check and update.
        flag_col_dict: Dictionary of names of the data column and flag column.

    Returns:
        A DataFrame with the flag column updated for missing values in the specified data column.
    """
    flag_val = core_flag_config["missing"].id

    for data_col_name, flag_col_name in flag_col_dict.items():
        df = df.with_columns(
            pl.when(pl.col(data_col_name).is_null() | pl.col(data_col_name).is_nan())
            .then(pl.col(flag_col_name) + flag_val)
            .otherwise(pl.col(flag_col_name))
            .alias(flag_col_name)
        )
    return df
