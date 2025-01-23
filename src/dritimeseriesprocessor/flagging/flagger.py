"""Util functions for managing flag data"""

import logging

import polars as pl

from dritimeseriesprocessor.__metadata__.config_core_flags import core_flag_config
from dritimeseriesprocessor.infilling.infiller import infill_flag_column_name
from dritimeseriesprocessor.preprocessing.preprocessor import pr_flag_column_name
from dritimeseriesprocessor.quality_control.quality_controller import qc_flag_column_name
from time_series import TimeSeries

logger = logging.getLogger(__name__)


CORE_FLAG_SYS_NAME = "core_flags"


def missing_expr(column_name: str) -> pl.Expr:
    """Return expression for missing values in column.

    Args:
        column_name: Data column name

    Returns:
        Expression for missing values
    """
    return pl.col(column_name).is_null() | pl.col(column_name).is_nan()


def core_flag_column_name(column: str) -> str:
    """Return flag column name for given data column name.

    Args:
        column: Data column name

    Returns:
        Flag column name
    """
    return f"{column}_FLAG"


def initialise_core_flag_system(ts: TimeSeries) -> TimeSeries:
    """Setup core flag system in TimeSeries object.

    Args:
        ts: The input TimeSeries object.

    Returns:
        The TimeSeries with the core flag system added.
    """
    # Initialise core flag system within TimeSeries object
    core_flags_dict = {name: flag.id for name, flag in core_flag_config.items()}
    ts.add_flag_system(CORE_FLAG_SYS_NAME, core_flags_dict)

    return ts


def add_initial_core_flags(ts: TimeSeries) -> TimeSeries:
    """Setup core flags and initialise with "unchecked" and "missing" flags.

    Args:
        ts: The input TimeSeries object.

    Returns:
        The TimeSeries with the flag columns added
    """
    ts = initialise_core_flag_system(ts)

    for data_col_name in ts.data_columns:
        flag_col_name = core_flag_column_name(data_col_name)
        ts.init_flag_column(CORE_FLAG_SYS_NAME, flag_col_name)

        # Set all as unchecked
        ts.add_flag(flag_col_name, "unchecked", pl.lit(True))
        # Flag missing values
        ts.add_flag(flag_col_name, "missing", missing_expr(data_col_name))

    return ts


def update_preprocess_core_flags(ts: TimeSeries) -> TimeSeries:
    """Add 'corrected' flag where data has been corrected in preprocessing. This is
    determined by where there is a preprocessing flag.

    Args:
        ts: The input TimeSeries object.

    Returns:
        The TimeSeries with the flag columns added
    """
    for data_col_name in ts.data_columns:
        core_flag_col_name = core_flag_column_name(data_col_name)
        pr_flag_col_name = pr_flag_column_name(data_col_name)

        # Check core flags are set up.
        if CORE_FLAG_SYS_NAME not in ts.flag_systems:
            ts = initialise_core_flag_system(ts)

        if core_flag_col_name not in ts.flag_columns:
            ts.init_flag_column(CORE_FLAG_SYS_NAME, core_flag_col_name)

        # Do nothing if there is no preprocess flag column.
        if pr_flag_col_name not in ts.flag_columns:
            continue

        # Add corrected core flag where preprocess flag is not 0.
        expr = pl.col(pr_flag_col_name) != 0
        ts.add_flag(core_flag_col_name, "corrected", expr)

    return ts


def update_quality_control_core_flags(ts: TimeSeries) -> TimeSeries:
    """Remove 'unchecked' flag and add 'removed' flag where data has been removed.

    Args:
        ts: The input TimeSeries object.

    Returns:
        The TimeSeries with the flag columns added
    """
    for data_col_name in ts.data_columns:
        core_flag_col_name = core_flag_column_name(data_col_name)
        qc_flag_col_name = qc_flag_column_name(data_col_name)

        # Check core flags are set up.
        if CORE_FLAG_SYS_NAME not in ts.flag_systems:
            ts = initialise_core_flag_system(ts)

        if core_flag_col_name not in ts.flag_columns:
            ts.init_flag_column(CORE_FLAG_SYS_NAME, core_flag_col_name)

        # Do nothing if there is no QC flag column.
        if qc_flag_col_name not in ts.flag_columns:
            continue

        # Remove unchecked flag where the is a non-null QC flag.
        expr = ~missing_expr(qc_flag_col_name)
        ts.remove_flag(core_flag_col_name, "unchecked", expr)

        # Add removed flag, the data value must be missing as well as have a QC flag value not 0.
        expr = (missing_expr(data_col_name)) & (pl.col(qc_flag_col_name) != 0)
        ts.add_flag(core_flag_col_name, "removed", expr)
        # If data is removed, remove the corrected flag.
        ts.remove_flag(core_flag_col_name, "corrected", expr)

    return ts


def update_infill_core_flags(ts: TimeSeries) -> TimeSeries:
    """Add 'estimated' flag where data has been infilled. This is
    determined by where there is an infill flag.

    Args:
        ts: The input TimeSeries object.

    Returns:
        The TimeSeries with the flag columns added
    """
    flag_col_dict = {}
    for data_col_name in ts.data_columns:
        core_flag_col_name = core_flag_column_name(data_col_name)
        infill_flag_col_name = infill_flag_column_name(data_col_name)

        if core_flag_col_name not in ts.supplementary_columns:
            ts.init_supplementary_column(core_flag_col_name, 0)

        if infill_flag_col_name not in ts.supplementary_columns:
            continue
        else:
            # Build dict that connects data col with its infill flag and core flag
            # columns.
            flag_col_dict[data_col_name] = {
                "core_flag_col": core_flag_col_name,
                "infl_flag_col": infill_flag_col_name,
            }

    ts.df = add_estimated_flag(ts.df, flag_col_dict)

    return ts


def remove_unchecked_flag(df: pl.DataFrame, flag_col_dict: dict) -> pl.DataFrame:
    """
    Remove "unchecked" flag for all values in df with a QC flag column.

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
            pl.when(pl.col(flag_cols["pr_flag_col"]).is_not_null())
            .then(pl.col(flag_cols["core_flag_col"]) + flag_val)
            .otherwise(pl.col(flag_cols["core_flag_col"]))
            .alias(flag_cols["core_flag_col"])
        )
    return df


def add_estimated_flag(df: pl.DataFrame, flag_col_dict: dict) -> pl.DataFrame:
    """
    Add a flag for values that have been estimated by infilling.
    Note, the infilling flag column must be non-null.

    Args:
        df: The Polars DataFrame to check and update.
        flag_col_dict: Dictionary of names of the data column with core and infill flag column names.

    Returns:
        A DataFrame with the flag column updated for removed values in the specified data column.
    """
    flag_val = core_flag_config["estimated"].id

    for flag_cols in flag_col_dict.values():
        df = df.with_columns(
            pl.when(pl.col(flag_cols["infl_flag_col"]).is_not_null())
            .then(pl.col(flag_cols["core_flag_col"]) + flag_val)
            .otherwise(pl.col(flag_cols["core_flag_col"]))
            .alias(flag_cols["core_flag_col"])
        )
    return df
