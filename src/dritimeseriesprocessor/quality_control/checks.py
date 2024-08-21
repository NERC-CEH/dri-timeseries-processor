"""Quality control checks to be run."""

import logging

import polars as pl

import dritimeseriesprocessor.__metadata__.config_quality_control as qc_config
import dritimeseriesprocessor.quality_control.utils as qc_utils

logger = logging.getLogger(__name__)


def range_qc(df: pl.DataFrame, column: str, resolution: str = "PT30M") -> pl.DataFrame:
    """
    Test values falls between min and max range.

    This function checks if the given column has values
    within the expected range and applies a quality control
    flag to the specified column if it is.

    Args:
        df: The input DataFrame containing the data to be tested.
        column: The name of the column to which the flag will be applied.
        resolution: Resolution of the data. Defaults to PT30M.

    Returns:
        The DataFrame with the quality control flag applied.
    """
    range_thresholds = qc_config.get_qc_config("range_thresholds")
    range_threshold = range_thresholds.get(column)

    if range_threshold is None:
        logger.warning(f"Can not run range test. No {column} data provided")
        return df

    default_min_val, default_max_val = qc_utils.get_default_range_vals(range_threshold, resolution)

    if default_min_val is None:
        msg = f"No default min/max values set for {column} range test"
        logger.error(msg)
        raise ValueError(msg)

    # Add flag column, initially with all 0's
    flag_col_name = f"{column}_QCFLAG"
    df = df.with_columns(pl.lit(0).alias(flag_col_name))

    # Perform range checks per site, as they can have different min/max thresholds
    sites = df.unique(subset="SITE_ID").select("SITE_ID").to_series().to_list()

    for site in sites:
        # Check for site specific min/max values
        min_val, max_val = qc_utils.get_site_range_vals(range_threshold, site, resolution)

        if min_val is None:
            min_val = default_min_val
            max_val = default_max_val

        df = df.with_columns(
            pl.when(pl.col("SITE_ID").eq(site) & (pl.col(column).lt(min_val) | pl.col(column).gt(max_val)))
            .then(qc_config.qc_tests["RANGE"]["id"])
            .otherwise(pl.col(flag_col_name))
            .alias(flag_col_name)
        )

    return df


def battery_voltage_qc(df: pl.DataFrame, column: str) -> pl.DataFrame:
    """
    Test the battery voltage level is above the threshold.

    This function checks if the battery voltage ('BATTV' column)
    is below a certain threshold and applies a quality control flag
    to the specified column if it is.

    Args:
        df: The input DataFrame containing the data to be tested.
        column: The name of the column to which the flag will be applied.

    Returns:
        Quality controlled dataframe.
    """
    if "BATTV" not in df:
        logger.warning("Can not run Battery voltage test. No BATTV data provided")
        return df

    else:
        battv_config = qc_config.get_qc_config("battv_threshold")

        flags = qc_utils.col_comparison_test(
            df.select(column), df["BATTV"], battv_config.threshold, flag=qc_config.qc_tests["BATTV"]["id"], op="<"
        )
        return qc_utils.add_qcflag_column(df, flags, column)


def soilmet_scans_qc(df: pl.DataFrame, column: str) -> pl.DataFrame:
    """
    Test the soilmet scans value is above the threshold.

    This function checks if the soilmet scans value ('SCANS' column)
    is below a certain threshold and applies a quality control flag to
    the appropriate columns if it is.

    Args:
        df: The input DataFrame containing the data to be tested.
        column: The name of the column to which the quality
                control flag will be applied.

    Returns:
        The DataFrame with the quality control flag
        applied, or returned as is if the 'BATTV' column is not
        present in the input DataFrame.
    """
    if "SCANS" not in df:
        logger.warning("Can not run soilmet scans test. No SCANS column in data.")
        return df

    else:
        soilmet_scan_config = qc_config.get_qc_config("soilmet_scan_threshold")

        flags = qc_utils.col_comparison_test(
            df.select(column),
            df["SCANS"],
            soilmet_scan_config.threshold,
            flag=qc_config.qc_tests["SCANS"]["id"],
            op="<",
        )

        return qc_utils.add_qcflag_column(df, flags, column)


def error_codes_qc(df: pl.DataFrame, column: str) -> pl.DataFrame:
    """Add QC flag for expected error codes.

    Args:
        df: The input DataFrame
        column: The name of the column to which the quality
                control flag will be applied.

    Returns:
        The DataFrame with the quality control flag applied.
    """
    error_codes = [7999, 8999]

    for error_code in error_codes:
        flags = qc_utils.col_comparison_test(
            df.select(column),
            df[column],
            error_code,
            flag=qc_config.qc_tests["ERROR_CODES"]["id"],
            op="==",
        )

        df = qc_utils.add_qcflag_column(df, flags, column)

    return df
