"""Util functions for managing flag data"""

import logging

import polars as pl
import time_stream as ts

from new_processor.utils.polars_utils import missing_expr, not_missing_expr
from new_processor.routers.metadata_router import fetch_core_flags
from new_processor.api_models.operations.flags import CoreFlagResponse

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


def corrs_flag_column_name(column: str) -> str:
    """
    Return column name of corrections flag column for a given variable column.

    Args:
        column: Data column name

    Returns:
        Flag column name
    """
    return f"{column}_CORRS_FLAG"


def qc_flag_column_name(column: str) -> str:
    """
    Return column name of QC flag column for a given variable column.

    Args:
        column: Data column name

    Returns:
        Flag column name
    """
    return f"{column}_QC_FLAG"


def infill_flag_column_name(column: str) -> str:
    """
    Return column name of infill flag column for a given variable column.

    Args:
        column: Data column name

    Returns:
        Flag column name
    """
    return f"{column}_INFILL_FLAG"


def initialise_core_flag_system(tf: ts.TimeFrame) -> ts.TimeFrame:
    """Setup core flag system in ts.TimeFrame object.

    Args:
        tf: The input ts.TimeFrame object.

    Returns:
        The ts.TimeFrame with the core flag system added.
    """
    # Initialise core flag system within ts.TimeFrame object
    response = fetch_core_flags()
    parsed = CoreFlagResponse.model_validate(response)

    core_flags_dict = {name: flag.id for name, flag in parsed.core_flags.items()}
    tf.register_flag_system(CORE_FLAG_SYS_NAME, core_flags_dict)

    return tf


def add_initial_core_flags(tf: ts.TimeFrame) -> ts.TimeFrame:
    """Setup core flags and initialise with "unchecked" and "missing" flags.

    Args:
        tf: The input ts.TimeFrame object.

    Returns:
        The ts.TimeFrame with the flag columns added
    """
    tf = initialise_core_flag_system(tf)

    for data_col_name in tf.data_columns:
        flag_col_name = core_flag_column_name(data_col_name)
        tf.init_flag_column(data_col_name, CORE_FLAG_SYS_NAME, flag_col_name)

        # Set all as unchecked
        tf.add_flag(flag_col_name, "unchecked", pl.lit(True))
        # Flag missing values
        tf.add_flag(flag_col_name, "missing", missing_expr(data_col_name))

    return tf


def update_corrections_core_flags(tf: ts.TimeFrame) -> ts.TimeFrame:
    """Add 'corrected' flag where data has been corrected. This is determined by where there is a corrections flag.

    Args:
        tf: The input ts.TimeFrame object.

    Returns:
        The ts.TimeFrame with the flag columns added
    """
    for data_col_name in tf.data_columns:
        core_flag_col_name = core_flag_column_name(data_col_name)
        corrs_flag_col_name = corrs_flag_column_name(data_col_name)

        if core_flag_col_name not in tf.flag_columns:
            raise ValueError(f"Core flag column {core_flag_col_name} not found in ts.TimeFrame.")

        # Do nothing if there is no corrections flag column.
        if corrs_flag_col_name not in tf.flag_columns:
            continue

        # Add corrected core flag where corrections flag is not 0.
        expr = pl.col(corrs_flag_col_name) != 0
        tf.add_flag(core_flag_col_name, "corrected", expr)

    return tf


def update_quality_control_core_flags(tf: ts.TimeFrame) -> ts.TimeFrame:
    """Remove 'unchecked' flag and add 'removed' flag where data has been removed.

    Args:
        tf: The input ts.TimeFrame object.

    Returns:
        The ts.TimeFrame with the flag columns added
    """
    for data_col_name in tf.data_columns:
        core_flag_col_name = core_flag_column_name(data_col_name)
        qc_flag_col_name = qc_flag_column_name(data_col_name)

        if core_flag_col_name not in tf.flag_columns:
            raise ValueError(f"Core flag column {core_flag_col_name} not found in ts.TimeFrame.")

        # Do nothing if there is no QC flag column.
        if qc_flag_col_name not in tf.flag_columns:
            continue

        # Remove unchecked flag where there is a non-null QC flag.
        expr = not_missing_expr(qc_flag_col_name)
        tf.remove_flag(core_flag_col_name, "unchecked", expr)

        # Add removed flag, the data value must be missing as well as have a QC flag value not 0.
        expr = (missing_expr(data_col_name)) & (pl.col(qc_flag_col_name) != 0)
        tf.add_flag(core_flag_col_name, "removed", expr)
        # If data is removed, remove the corrected flag.
        tf.remove_flag(core_flag_col_name, "corrected", expr)

    return tf


def update_infill_core_flags(tf: ts.TimeFrame) -> ts.TimeFrame:
    """Add 'estimated' flag where data has been infilled. This is
    determined by where there is an infill flag.

    Args:
        tf: The input ts.TimeFrame object.

    Returns:
        The ts.TimeFrame with the flag columns added
    """
    for data_col_name in tf.data_columns:
        core_flag_col_name = core_flag_column_name(data_col_name)
        infill_flag_col_name = infill_flag_column_name(data_col_name)

        if core_flag_col_name not in tf.flag_columns:
            raise ValueError(f"Core flag column {core_flag_col_name} not found in ts.TimeFrame.")

        # Do nothing if there is no infilling flag column.
        if infill_flag_col_name not in tf.flag_columns:
            continue

        # Add estimated core flag where infill flag is not 0.
        expr = pl.col(infill_flag_col_name) != 0
        tf.add_flag(core_flag_col_name, "estimated", expr)

    return tf
