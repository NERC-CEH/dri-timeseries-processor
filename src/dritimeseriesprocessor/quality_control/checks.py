import logging

import polars as pl

from dritimeseriesprocessor.__metadata__.config_quality_control import get_qc_config
from dritimeseriesprocessor.quality_control.utils import (
    column_threshold_check,
    get_site_range_values,
    get_site_spike_threshold,
)

logger = logging.getLogger(__name__)


def battery_voltage_check(df: pl.DataFrame, column: str, flag_column: str, flag_id: int) -> pl.DataFrame:
    """Check that the battery voltage level is above the threshold.

    This function checks if the battery voltage ('BATTV' column) is below a certain threshold
    and applies a quality control flag to the specified column if it is.

    Args:
        df: The input DataFrame containing the data to be tested.
        column: The name of the column to which the quality control flag will be applied.
        flag_column: The column to which flag value should be added.
        flag_id: The ID of the quality control flag that should be applied to data that fail this check.

    Returns:
        The DataFrame with the quality control flag applied.
    """
    battv_config = get_qc_config("battv_threshold")
    df = column_threshold_check(df, "BATTV", column, flag_column, battv_config.threshold, "<", flag_id)

    return df


def range_check(df: pl.DataFrame, column: str, flag_column: str, flag_id: int) -> pl.DataFrame:
    """Check values falls between min and max range, applying a quality control flag if outside of range.

    Min and max range values are defined per site, per variable and per time resolution.

    Args:
        df: The input DataFrame containing the data to be tested.
        column: The name of the column to which the quality control flag will be applied.
        flag_column: The column to which flag value should be added.
        flag_id: The ID of the quality control flag that should be applied to data that fail this check.

    Returns:
         The DataFrame with the quality control flag applied.
    """
    resolution = "PT30M"  # TODO: Get this from somewhere

    # Perform range checks per site, as they can have different min/max thresholds
    sites = df.get_column("SITE_ID").unique()
    for site in sites:
        min_val, max_val = get_site_range_values(site, column, resolution)

        df = df.with_columns(
            pl.when(pl.col("SITE_ID").eq(site) & (pl.col(column).lt(min_val) | pl.col(column).gt(max_val)))
            .then(pl.col(flag_column).add(flag_id))
            .otherwise(pl.col(flag_column))
            .alias(flag_column)
        )

    return df


def soilmet_scans_check(df: pl.DataFrame, column: str, flag_column: str, flag_id: int) -> pl.DataFrame:
    """Check the soilmet scans value is above an acceptable threshold.

    Args:
        df: The input DataFrame containing the data to be tested.
        column: The name of the column to which the quality control flag will be applied.
        flag_column: The column to which flag value should be added.
        flag_id: The ID of the quality control flag that should be applied to data that fail this check.

    Returns:
        The DataFrame with the quality control flag applied.
    """
    soilmet_scan_config = get_qc_config("soilmet_scan_threshold")
    df = column_threshold_check(df, "SCANS", column, flag_column, soilmet_scan_config.threshold, "<", flag_id)

    return df


def error_codes_check(df: pl.DataFrame, column: str, flag_column: str, flag_id: int) -> pl.DataFrame:
    """Add QC flag for expected error codes.

    Args:
        df: The input DataFrame
        column: The name of the column to which the quality control flag will be applied.
        flag_column: The column to which flag value should be added.
        flag_id: The ID of the quality control flag that should be applied to data that fail this check.

    Returns:
        The DataFrame with the quality control flag applied.
    """
    error_codes = [7999, 8999]  # TODO: Get these values from somewhere
    for error_code in error_codes:
        df = column_threshold_check(df, column, column, flag_column, error_code, "==", flag_id)

    return df


def spike_check(df: pl.DataFrame, column: str, flag_column: str, flag_id: int) -> pl.DataFrame:
    """Assess the total difference between a value and its neighbours and remove any skew in the size of the
    differences with each neighbour.

    Note that first and last value in the timeseries cannot be assessed, as they don't have previous/next values to
    assess spike against.

    Args:
        df: The input DataFrame containing the data to be tested.
        column: The name of the column to which the quality control flag will be applied.
        flag_column: The column to which flag value should be added.
        flag_id: The ID of the quality control flag that should be applied to data that fail this check.

    Returns:
        pl.DataFrame: The DataFrame with the quality control flag applied.
    """
    resolution = "PT30M"  # TODO: Get this from somewhere

    # Perform spike checks per site, as they can have different spike thresholds
    sites = df.get_column("SITE_ID").unique()
    for site in sites:
        # Get the site specific (or default) spike threshold to use for check
        spike_threshold = get_site_spike_threshold(site, column, resolution)

        # Make a new dataframe for doing data shifting
        tst_spikes = df.clone()

        # Difference between value and previous value
        tst_spikes = tst_spikes.with_columns(pl.col(column).shift(1).alias("prev_val"))
        tst_spikes = tst_spikes.with_columns((pl.col(column).sub(pl.col("prev_val"))).alias("diff_prev"))

        # Difference between next value and value
        tst_spikes = tst_spikes.with_columns(pl.col(column).shift(-1).alias("next_val"))
        tst_spikes = tst_spikes.with_columns((pl.col("next_val").sub(pl.col(column))).alias("diff_next"))

        # Calculate overall combined difference, absolute value
        tst_spikes = tst_spikes.with_columns((pl.col("diff_prev").sub(pl.col("diff_next"))).abs().alias("d"))

        # Calculate the absolute skew in differences each side of the data value.
        tst_spikes = tst_spikes.with_columns(
            (pl.col("diff_prev").abs().sub(pl.col("diff_next").abs())).abs().alias("skew")
        )

        # Calculate the total difference minus the skew
        tst_spikes = tst_spikes.with_columns((pl.col("d").sub(pl.col("skew"))).alias("d_no_skew"))

        # As we have summed the differences, we should double the threshold
        spikes = tst_spikes.get_column("d_no_skew").gt(spike_threshold * 2.0)

        df = df.with_columns(
            pl.when(spikes).then(pl.col(flag_column).add(flag_id)).otherwise(pl.col(flag_column)).alias(flag_column)
        )

    return df


QC_CHECKS = {
    "BATTV": battery_voltage_check,
    "RANGE": range_check,
    "SCANS": soilmet_scans_check,
    "ERROR_CODES": error_codes_check,
    "SPIKE": spike_check,
}
