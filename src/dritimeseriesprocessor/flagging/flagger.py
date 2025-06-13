"""Util functions for managing flag data"""

import logging

import polars as pl
from time_stream import TimeSeries

from dritimeseriesprocessor.__metadata__.config_core_flags import core_flag_config
from dritimeseriesprocessor.utils import missing_expr, not_missing_expr

logger = logging.getLogger(__name__)


CORE_FLAG_SYS_NAME = "core_flags"


def core_flag_column_name(column: str) -> str:
    """Return flag column name for given data column name.

    Args:
        column: Data column name

    Returns:
        Flag column name
    """
    return f"{column}_CORE_FLAG"


def pr_flag_column_name(column: str) -> str:
    """Return column name of preprocess flag column for a given variable column."""
    return f"{column}_PR_FLAG"


def qc_flag_column_name(column: str) -> str:
    """Return column name of QC flag column for a given variable column."""
    return f"{column}_QC_FLAG"


def infill_flag_column_name(column: str) -> str:
    """Return column name of infill flag column for a given variable column."""
    return f"{column}_INFILL_FLAG"


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

        if core_flag_col_name not in ts.flag_columns:
            raise ValueError(f"Core flag column {core_flag_col_name} not found in TimeSeries.")

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

        if core_flag_col_name not in ts.flag_columns:
            raise ValueError(f"Core flag column {core_flag_col_name} not found in TimeSeries.")

        # Do nothing if there is no QC flag column.
        if qc_flag_col_name not in ts.flag_columns:
            continue

        # Remove unchecked flag where there is a non-null QC flag.
        expr = not_missing_expr(qc_flag_col_name)
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
    for data_col_name in ts.data_columns:
        core_flag_col_name = core_flag_column_name(data_col_name)
        infill_flag_col_name = infill_flag_column_name(data_col_name)

        if core_flag_col_name not in ts.flag_columns:
            raise ValueError(f"Core flag column {core_flag_col_name} not found in TimeSeries.")

        # Do nothing if there is no infilling flag column.
        if infill_flag_col_name not in ts.flag_columns:
            continue

        # Add estimated core flag where infill flag is not 0.
        expr = pl.col(infill_flag_col_name) != 0
        ts.add_flag(core_flag_col_name, "estimated", expr)

    return ts
