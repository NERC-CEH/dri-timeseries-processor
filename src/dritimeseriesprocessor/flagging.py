"""Util functions for managing flag data"""

import logging

import polars as pl

from dritimeseriesprocessor.__metadata__.config_core_flags import core_flag_config
from dritimeseriesprocessor.preprocessing.preprocessor import prpr_flag_column_name
from dritimeseriesprocessor.quality_control.utils import qc_flag_column_name
from time_series import TimeSeries

logger = logging.getLogger(__name__)


def core_flag_column_name(column: str) -> str:
    """Return flag column name for given data column name.

    Args:
        col_name: Data column name

    Returns:
        Flag column name
    """
    return f"{column}_FLAG"


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
    for data_col_name in ts.data_columns:
        flag_col_name = core_flag_column_name(data_col_name)
        flag_col_dict[data_col_name] = flag_col_name
        ts.init_supplementary_column(flag_col_name, 0)

    flag_col_names = flag_col_dict.values()

    ts.df = add_unchecked_flag(ts.df, flag_col_names)
    ts.df = add_missing_flag(ts.df, flag_col_dict)

    return ts


def preprocess_core_flags(ts: TimeSeries) -> TimeSeries:
    """Add 'corrected' flag where data has been coreected in preprocessing
    Remove preprocessing flag column.

    Args:
        ts: The input TimeSeries object.

    Returns:
        The TimeSeries with the flag columns added
    """
    flag_col_dict = {}
    for data_col_name in ts.data_columns:
        core_flag_col_name = core_flag_column_name(data_col_name)
        prpr_flag_col_name = prpr_flag_column_name(data_col_name)

        if prpr_flag_col_name not in ts.df.columns:
            continue
        else:
            flag_col_dict[data_col_name] = {
                "core_flag_col": core_flag_col_name,
                "prpr_flag_col": prpr_flag_col_name,
            }

    ts.df = add_corrected_flag(ts.df, flag_col_dict)

    return ts


def quality_control_core_flags(ts: TimeSeries) -> TimeSeries:
    """Remove 'unchecked' flag and add 'removed' flag where data has been removed

    Args:
        ts: The input TimeSeries object.

    Returns:
        The TimeSeries with the flag columns added
    """
    flag_col_dict = {}
    for data_col_name in ts.data_columns:
        core_flag_col_name = core_flag_column_name(data_col_name)
        qc_flag_col_name = qc_flag_column_name(data_col_name)

        if qc_flag_col_name not in ts.df.columns:
            continue
        else:
            flag_col_dict[data_col_name] = {
                "core_flag_col": core_flag_col_name,
                "qc_flag_col": qc_flag_col_name,
            }

    ts.df = remove_unchecked_flag(ts.df, flag_col_dict)
    ts.df = add_removed_flag(ts.df, flag_col_dict)

    return ts


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


def remove_unchecked_flag(df: pl.DataFrame, flag_col_dict: dict) -> pl.DataFrame:
    """
    Add "unchecked" flag to all values in flag column.

    NOTE. This is currently very crude and assumes the unchhecked flag has already
    been added to all values.

    Args:
        df: The dataframe to update
        flag_col_dict: Dictionary of names of the data column with core and qc flag column names.

    Returns:
        Updated dataframe
    """
    flag_val = core_flag_config["unchecked"].id

    for flag_cols in flag_col_dict.values():
        df = df.with_columns(
            pl.when(pl.col(flag_cols["qc_flag_col"]).is_not_null())
            .then(pl.col(flag_cols["core_flag_col"]) - flag_val)
            .otherwise(pl.col(flag_cols["core_flag_col"]))
            .alias(flag_cols["core_flag_col"])
        )
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


def add_removed_flag(df: pl.DataFrame, flag_col_dict: dict) -> pl.DataFrame:
    """
    Add a flag for values that have been removed by QC.
    Note, the value must be None (like) AND have a QC flag value > 0.

    Args:
        df: The Polars DataFrame to check and update.
        flag_col_dict: Dictionary of names of the data column with core and qc flag column names.

    Returns:
        A DataFrame with the flag column updated for removed values in the specified data column.
    """
    flag_val = core_flag_config["removed"].id

    for data_col_name, flag_cols in flag_col_dict.items():
        df = df.with_columns(
            pl.when(
                (pl.col(data_col_name).is_null() | pl.col(data_col_name).is_nan())
                & (pl.col(flag_cols["qc_flag_col"]) > 0)
            )
            .then(pl.col(flag_cols["core_flag_col"]) + flag_val)
            .otherwise(pl.col(flag_cols["core_flag_col"]))
            .alias(flag_cols["core_flag_col"])
        )
    return df


def add_corrected_flag(df: pl.DataFrame, flag_col_dict: dict) -> pl.DataFrame:
    """
    Add a flag for values that have been corrected by preprocessing.
    Note, the preprocess flag column must be non-null

    Args:
        df: The Polars DataFrame to check and update.
        flag_col_dict: Dictionary of names of the data column with core and preprocess flag column names.

    Returns:
        A DataFrame with the flag column updated for removed values in the specified data column.
    """
    flag_val = core_flag_config["corrected"].id

    for flag_cols in flag_col_dict.values():
        df = df.with_columns(
            pl.when(pl.col(flag_cols["prpr_flag_col"]).is_not_null())
            .then(pl.col(flag_cols["core_flag_col"]) + flag_val)
            .otherwise(pl.col(flag_cols["core_flag_col"]))
            .alias(flag_cols["core_flag_col"])
        )
    return df
