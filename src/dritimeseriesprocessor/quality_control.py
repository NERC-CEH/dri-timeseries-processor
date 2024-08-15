import logging

import polars as pl

import dritimeseriesprocessor.config_quality_control as qc_config

logger = logging.getLogger(__name__)


def add_qcflag_column(df: pl.DataFrame, flags: pl.DataFrame, col_name: str) -> pl.DataFrame:
    """
    Create QC flag column.
    If a quality control flag column already exists for the specified column, the new
    flags are added to the existing ones.
    If no quality control flag column exists, a new column is appended to the DataFrame.

    -----------------
    Args:
        df: Dataframe to add flags to.
        flags: Flag data
        col_name: Name of column which was tested

    Returns:
        Polars DataFrame
    """
    flag_col_name = f"{col_name}_QCFLAG"
    flags = flags.rename({col_name: flag_col_name})

    if flag_col_name in df:
        # Add flag values onto existing values
        df = df.with_columns(pl.col(flag_col_name) + flags[flag_col_name])
    else:
        # Append new column
        df = df.hstack(flags)

    return df


def col_comparison_test(
    data: pl.DataFrame, test_col: pl.Series, threshold: float, flag: int, op: str = ">", flag_na: bool = False
) -> pl.DataFrame:
    """
    Generic test function for when a single column of data has implications
    for other columns in the data.

    For example, we would look at the battery voltage column (the
    test_col), compare it to the threshold using the op (which rows are <
    threshold), then all columns (variables) given in data would get the low
    battery flag.

    -----------------
    Args:
        data: This must have only the columns wanted for flagging
        test_col: The column of data that determines which rows get flagged
        threshold: Threshold value
        flag: The flag value used
        op: What comparison to make, see operator_map.
        flag_na: Comparison tests against NaNs will always result in False.
            So by default, NaN values will not cause data in data to be
            flagged. Set this to True to change that.

    Returns:
        Polars DataFrame with flags applied across all columns.
    """

    # Define the operation map for polars
    operator_map = {
        ">": test_col > threshold,
        ">=": test_col >= threshold,
        "<": test_col < threshold,
        "<=": test_col <= threshold,
        "==": test_col == threshold,
        "!=": test_col != threshold,
    }

    # Get the requested operator
    if op not in operator_map:
        raise ValueError(f"{op} is an invalid operator, use: {', '.join(operator_map.keys())}")

    # Apply the operator to the Series
    flag_col = operator_map[op]

    # Handle NaN cases if flag_na is True
    if flag_na:
        flag_col = flag_col | test_col.is_null()

    # Cast the flag column to integers and replace True (1) with the flag value
    flag_col = flag_col.cast(pl.Int32).replace(1, flag)

    # Apply the same flags to all columns in the given data
    flagged_data = data.with_columns([flag_col.alias(col) for col in data.columns])

    return flagged_data


def range_test(df: pl.DataFrame, column: str) -> pl.DataFrame:
    """
    Test values falls between min and max range.

    This function checks if the given column has values within the expected range
    and applies a quality control flag to the specified column if it is.

    Args:
        df: The input DataFrame containing the data to be tested.
        column: The name of the column to which the quality control flag will be applied.

    Returns:
        pl.DataFrame: The DataFrame with the quality control flag applied.
    """
    resolution = "PT30M"

    range_thresholds = qc_config.get_qc_config("range_thresholds")
    range_threshold = range_thresholds.get(column)
    if range_threshold is None:
        logger.warning(f"Can not run range test. No {column} data provided")
        return df

    default_min_val = None
    default_max_val = None
    # Establish defaults
    for range_thres_def in range_threshold.defaults:
        if range_thres_def.resolutions is None:
            # Default regardless of resolution
            default_min_val = range_thres_def.min_value
            default_max_val = range_thres_def.max_value

        elif resolution in range_thres_def.resolutions:
            # Defaults found for specific resolution
            default_min_val = range_thres_def.min_value
            default_max_val = range_thres_def.max_value
            break

    if default_min_val is None:
        msg = f"No default min/max values set for {column} range test"
        logger.error(msg)
        raise ValueError(msg)

    # Perform range checks per site, as they can have different min/max thresholds
    sites = df.unique(subset="SITE_ID").select("SITE_ID").to_series().to_list()

    site_dfs = []
    for site in sites:
        # Check for site specific min/max values
        for range_thres_site in range_threshold.sites:
            if range_thres_site.site_id == site and (
                range_thres_site.resolutions is None or resolution in range_thres_site.resolutions
            ):
                min_val = range_thres_site.min_value
                max_val = range_thres_site.max_value
                break
        else:
            min_val = default_min_val
            max_val = default_max_val

        site_df = df.filter(pl.col("SITE_ID") == site).select("time", "SITE_ID", column)

        # Find values that are out of range
        too_low = site_df.select(column) < min_val
        too_high = site_df.select(column) > max_val
        out_of_range = too_low.to_series() | too_high.to_series()

        flags = out_of_range.cast(pl.Int32).replace(1, 64).to_frame()
        site_df = add_qcflag_column(site_df, flags, column)
        site_dfs.append(site_df)

    all_site_dfs = pl.concat(site_dfs)
    all_site_dfs = all_site_dfs.drop(column)

    return df.join(all_site_dfs, on=("time", "SITE_ID"), how="left")


def battery_voltage_test(df: pl.DataFrame, column: str) -> pl.DataFrame:
    """
    Test the battery voltage level is above the threshold.

    This function checks if the battery voltage ('BATTV' column) is below a certain threshold
    and applies a quality control flag to the specified column if it is.

    Args:
        df: The input DataFrame containing the data to be tested.
        column: The name of the column to which the quality control flag will be applied.

    Returns:
        pl.DataFrame: The DataFrame with the quality control flag applied, or returned as is if
        the 'BATTV' column is not present in the input DataFrame.
    """
    if "BATTV" not in df:
        logger.warning("Can not run Battery voltage test. No BATTV data provided")
        return df

    battv_config = qc_config.get_qc_config("battv_threshold")

    power_flags = col_comparison_test(df.select(column), df["BATTV"], battv_config.threshold, flag=5, op="<")

    return add_qcflag_column(df, power_flags, column)


# Map method IDs to function
qc_test_map = {
    "BATTV": battery_voltage_test,
    "RANGE": range_test,
}


def run_qc(df: pl.DataFrame) -> pl.DataFrame:
    """
    Run data through Quality Control (QC) tests.

    This function applies a series of quality control tests to the input DataFrame based on
    the configuration specified in the qc_config module.

    Args:
        df: The input DataFrame containing the data to be quality controlled.

    Returns:
        pl.DataFrame: The DataFrame with quality control flags applied.

    Notes:
        - The function uses the variable_test_map and range_thresholds from the qc_config module.
        - For each variable specified in the variable_test_map, it applies the corresponding tests.
        - If a variable is not present in the input DataFrame, it is skipped.
        - If a test function is not available for a specified test, a warning is logged and the test is skipped.
        - The function modifies the input DataFrame in-place by adding or updating quality control flag columns.
    """
    qc_tests = qc_config.get_qc_config("qc_tests")

    for test_id, test_info in qc_tests.items():
        test_func = qc_test_map.get(test_id)
        if test_func is None:
            logger.warning(f"No QC function available for {test_info.test_name}")
            continue

        for variable in test_info.variables:
            logger.info(f"QC test: {test_info.test_name} for variable: {variable}")
            df = test_func(df, variable)

    return df
