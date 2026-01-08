"""Util functions for managing flag data"""

import logging

import polars as pl
import time_stream as ts

from new_processor.operations.flags.flag_names import (
    CORE_FLAG_SYS_NAME,
    core_flag_column_name,
    corrs_flag_column_name,
    infill_flag_column_name,
    qc_flag_column_name,
)
from new_processor.routers.metadata.local_loader import fetch_core_flags
from new_processor.utils.polars_utils import missing_expr, not_missing_expr

logger = logging.getLogger(__name__)


def initialise_core_flag_system(tf: ts.TimeFrame) -> ts.TimeFrame:
    """Setup core flag system in ts.TimeFrame object.

    Args:
        tf: The input ts.TimeFrame object.

    Returns:
        The ts.TimeFrame with the core flag system added.
    """
    # Initialise core flag system within ts.TimeFrame object
    response = fetch_core_flags()
    core_flags_dict = {name: flag.id for name, flag in response.core_flags.items()}
    tf.register_flag_system(CORE_FLAG_SYS_NAME, core_flags_dict)

    return tf


def add_initial_core_flags(tf: ts.TimeFrame, init_unchecked: bool = True, init_missing: bool = True) -> ts.TimeFrame:
    """Setup core flags and initialise with "unchecked" and "missing" flags.

    Args:
        tf: The input ts.TimeFrame object.
        init_unchecked: Whether to initialise the core flag with the unchecked flag
        init_missing: Whether to check for missing values to add the missing flag to

    Returns:
        The ts.TimeFrame with the flag columns added
    """
    tf = initialise_core_flag_system(tf)

    for data_col_name in tf.data_columns:
        flag_col_name = core_flag_column_name(data_col_name)
        tf.init_flag_column(data_col_name, CORE_FLAG_SYS_NAME, flag_col_name)

        if init_unchecked:
            # Set all as unchecked
            tf.add_flag(flag_col_name, "unchecked", pl.lit(True))

        if init_missing:
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

        expr_has_value = ~(pl.col(data_col_name).is_null() | pl.col(data_col_name).is_nan())
        expr_has_flag = pl.col(corrs_flag_col_name) != 0

        # Add corrected core flag where corrections flag is not 0 and the correction was successful.
        expr = expr_has_flag & expr_has_value
        tf.add_flag(core_flag_col_name, "corrected", expr)

        # Add unsuccessful_correction core flag where corrections flag is not 0 and the correction was NOT successful.
        expr = expr_has_flag & ~expr_has_value
        tf.add_flag(core_flag_col_name, "unsuccessful_correction", expr)

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

        # Add removed flag (and remove corrected flag) where the data value is missing and QC flag is not 0
        expr = (missing_expr(data_col_name)) & (pl.col(qc_flag_col_name) != 0)
        tf.add_flag(core_flag_col_name, "removed", expr)
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
