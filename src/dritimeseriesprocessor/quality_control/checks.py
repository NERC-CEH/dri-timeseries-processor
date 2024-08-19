import logging

import polars as pl

from dritimeseriesprocessor.__metadata__.config_quality_control import get_qc_config
from dritimeseriesprocessor.quality_control.utils import (
    column_threshold_check,
    get_site_range_values,
    initialise_qc_column,
)

logger = logging.getLogger(__name__)


def battery_voltage_check(df: pl.DataFrame, column: str, flag_id: int) -> pl.DataFrame:
    """Check that the battery voltage level is above the threshold.

    This function checks if the battery voltage ('BATTV' column) is below a certain threshold
    and applies a quality control flag to the specified column if it is.

    Args:
        df: The input DataFrame containing the data to be tested.
        column: The name of the column to which the quality control flag will be applied.
        flag_id: The ID of the quality control flag that should be applied to data that fail this check.

    Returns:
        The DataFrame with the quality control flag applied.
    """
    battv_config = get_qc_config("battv_threshold")
    df = column_threshold_check(df, "BATTV", column, battv_config.threshold, "<", flag_id)

    return df


def range_check(df: pl.DataFrame, column: str, flag_id: int) -> pl.DataFrame:
    """Check values falls between min and max range, applying a quality control flag if outside of range.

    Min and max range values are defined per site, per variable and per time resolution.

    Args:
        df: The input DataFrame containing the data to be tested.
        column: The name of the column to which the quality control flag will be applied.
        flag_id: The ID of the quality control flag that should be applied to data that fail this check.

    Returns:
         The DataFrame with the quality control flag applied.
    """
    resolution = "PT30M"  # TODO: Get this from somewhere

    df, qc_column = initialise_qc_column(df, column)

    # Perform range checks per site, as they can have different min/max thresholds
    sites = df.get_column("SITE_ID").unique()
    for site in sites:
        min_val, max_val = get_site_range_values(site, column, resolution)

        df = df.with_columns(
            pl.when(pl.col("SITE_ID").eq(site) & (pl.col(column).lt(min_val) | pl.col(column).gt(max_val)))
            .then(pl.col(qc_column).add(flag_id))
            .otherwise(pl.col(qc_column))
            .alias(qc_column)
        )

    return df


def soilmet_scans_check(df: pl.DataFrame, column: str, flag_id: int) -> pl.DataFrame:
    """Check the soilmet scans value is above an acceptable threshold.

    Args:
        df: The input DataFrame containing the data to be tested.
        column: The name of the column to which the quality control flag will be applied.
        flag_id: The ID of the quality control flag that should be applied to data that fail this check.

    Returns:
        The DataFrame with the quality control flag applied.
    """
    soilmet_scan_config = get_qc_config("soilmet_scan_threshold")
    df = column_threshold_check(df, "SCANS", column, soilmet_scan_config.threshold, "<", flag_id)

    return df


QC_CHECKS = {"BATTV": battery_voltage_check, "RANGE": range_check, "SCANS": soilmet_scans_check}
