"""Util functions for managing flag data"""

import logging

import polars as pl
import time_stream as ts

from dritimeseriesprocessor.models.domain_models.time_series_container import TimeSeriesContainer
from dritimeseriesprocessor.operations.flags.flag_names import (
    core_flag_column_name,
    corrs_flag_column_name,
    infill_flag_column_name,
    qc_flag_column_name,
)
from dritimeseriesprocessor.utils.polars_utils import missing_expr, not_missing_expr

logger = logging.getLogger(__name__)


def ensure_flag_column(
    tf: ts.TimeFrame,
    flag_column_name: str,
    flag_systems: dict[str, dict[str, int]],
    flag_column_schemes: dict[str, str],
) -> None:
    """Register the flag system and create a single flag column on a TimeFrame, if needed.

    Does nothing when the dataset does not define this flag column in its metadata, or when the flag
    system or column is already set up - existing flag columns are left untouched so their flag
    values are preserved. A dataset may define no flagging at all, in which case every flag column is
    skipped.

    Args:
        tf: The TimeFrame to set up flagging on.
        flag_column_name: The flag column to create (e.g. a core or QC flag column).
        flag_systems: All flag system definitions, keyed by system name.
        flag_column_schemes: Flag column names mapped to the flag system that governs them.
    """
    flag_system_name = flag_column_schemes.get(flag_column_name)
    if flag_system_name is None:
        # The dataset does not define this flag column - nothing to set up.
        return

    if flag_system_name not in tf.flag_systems:
        tf.register_flag_system(flag_system_name, flag_systems[flag_system_name])

    if flag_column_name not in tf.flag_columns:
        tf.init_flag_column(flag_system_name, flag_column_name)


def initialise_flag_systems(
    container: TimeSeriesContainer, flag_systems: dict[str, dict[str, int]]
) -> TimeSeriesContainer:
    """Initialise all flag systems that are defined in the metadata for this time series container

    Args:
        container: The time series container to initialise flags system on.
        flag_systems: Flag systems to initialise

    Returns:
        The container with the flag systems initialised
    """
    if container.data is None:
        return container

    for flag_column_name in container.flag_column_schemes:
        ensure_flag_column(container.data, flag_column_name, flag_systems, container.flag_column_schemes)

    return container


def add_initial_core_flags(
    container: TimeSeriesContainer, init_unchecked: bool = True, init_missing: bool = True
) -> TimeSeriesContainer:
    """Setup core flags and initialise with "unchecked" and "missing" flags.

    Args:
        container: The time series container to initialise core flags on.
        init_unchecked: Whether to initialise the core flag with the unchecked flag
        init_missing: Whether to check for missing values to add the missing flag to

    Returns:
        The container with the flag columns added to its data TimeFrame
    """
    if container.data is None:
        return container

    for data_col_name in container.data.data_columns:
        flag_col_name = core_flag_column_name(data_col_name)
        flag_system = container.flag_column_schemes.get(flag_col_name)

        if flag_system:
            if init_unchecked:
                # Set all as unchecked
                container.data.add_flag(flag_col_name, "unchecked", pl.lit(True))

            if init_missing:
                # Flag missing values
                container.data.add_flag(
                    flag_col_name, "missing", missing_expr(data_col_name, container.data.df[data_col_name].dtype)
                )

    return container


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
        expr = not_missing_expr(qc_flag_col_name, tf.df[qc_flag_col_name].dtype)
        tf.remove_flag(core_flag_col_name, "unchecked", expr)

        # Add removed flag (and remove corrected flag) where the data value is missing and QC flag is not 0
        expr = (missing_expr(data_col_name, tf.df[data_col_name].dtype)) & (pl.col(qc_flag_col_name) != 0)
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
