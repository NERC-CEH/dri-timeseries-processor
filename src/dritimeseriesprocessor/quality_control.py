import logging
from typing import Optional, Tuple

import polars as pl

import dritimeseriesprocessor.__metadata__.config_quality_control as qc_config

logger = logging.getLogger(__name__)


def create_flag_column_name(col_name: str) -> str:
    """
    Create QC flag column name for given column.

    -----------------
    Args:
        col_name: Name of original column

    Returns:
        string
    """
    return f"{col_name}_QCFLAG"


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
    flag_col_name = create_flag_column_name(col_name)
    flags = flags.rename({col_name: flag_col_name})

    if flag_col_name in df:
        # Add flag values onto existing values
        df = df.with_columns(pl.col(flag_col_name) + flags[flag_col_name])
    else:
        # Append new column
        df = df.hstack(flags)

    return df


def get_range_thresholds(
    range_config: qc_config.VariableThresholds,
    resolution: str,
    site_id: str,
) -> Tuple[Optional[float], Optional[float]]:
    """
    Get the default minimum and maximum values for a given resolution.

    This function searches through the default range thresholds and returns
    the min and max values based on the provided resolution. If no specific
    resolution is found, it returns the general default values.

    Parameters:
        range_config: The threshold object containing default values.
        resolution: The resolution for which the default range values are needed.
        site_id: Site identifier.

    Returns:
        Tuple[Optional[float], Optional[float]]: A tuple containing the minimum and maximum values.
                                                 Returns (None, None) if no values are found.
    """
    # Check for site specific min/max values
    for range_thres_site in range_config.sites:
        if range_thres_site.site_id == site_id and (
            resolution in range_thres_site.resolutions or len(range_thres_site.resolutions) == 0
        ):
            return range_thres_site.min_value, range_thres_site.max_value

    # No site specific values found, get min/max defaults
    min_val = None
    max_val = None
    for range_thres_def in range_config.defaults:
        if not range_thres_def.resolutions:
            # Default regardless of resolution
            min_val = range_thres_def.min_value
            max_val = range_thres_def.max_value

        elif resolution in range_thres_def.resolutions:
            # Defaults found for specific resolution
            min_val = range_thres_def.min_value
            max_val = range_thres_def.max_value
            break

    return min_val, max_val


def get_spike_threshold(
    spike_config: qc_config.VariableThresholds,
    resolution: str,
    site_id: str,
) -> Tuple[Optional[float], Optional[float]]:
    """
    Get the default spike threshold value for a given resolution.

    This function searches through the default spike thresholds and returns
    the threshold value based on the provided resolution. If no specific
    resolution is found, it returns the general default value.

    Parameters:
        spike_config: The config object containing default values.
        resolution: The resolution for which the default spike values are needed.
        site_id: Site identifier.

    Returns:
        Optional[float]: Returns None if no values are found.
    """
    # Check for site specific spike threshold
    for spike_thres_site in spike_config.sites:
        if spike_thres_site.site_id == site_id and (
            resolution in spike_thres_site.resolutions or len(spike_thres_site.resolutions == 0)
        ):
            return spike_thres_site.threshold

    # No site specific threshold found, get default
    threshold = None
    for spike_thres_def in spike_config.defaults:
        if not spike_thres_def.resolutions:
            # Default regardless of resolution
            threshold = spike_thres_def.threshold

        elif resolution in spike_thres_def.resolutions:
            # Defaults found for specific resolution
            threshold = spike_thres_def.threshold
            break

    return threshold


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


def range_test(df: pl.DataFrame, var_col_name: str, flag_col_name: str, site_id: str) -> pl.DataFrame:
    """
    Test values falls between min and max range.

    This function checks if the given column has values within the expected range
    and applies a quality control flag to the specified column if it is.

    Args:
        df: The input DataFrame containing the data to be tested.
        var_col_name: The name of the column to which the quality control will be applied.
        flag_col_name: The name of the column to which the quality control flags will be added.
        site_id: Site identifier

    Returns:
        pl.DataFrame: The DataFrame with the quality control flag applied.
    """
    # Place holder. We need to pass in the data resolution. As is, this means this test will
    # only work for 30min data.
    resolution = "PT30M"

    range_configs = qc_config.get_qc_config("range_thresholds")
    range_config = range_configs.get(var_col_name)
    if range_config is None:
        logger.warning(f"Can not run range test. No {var_col_name} data provided")
        return df

    min_val, max_val = get_range_thresholds(range_config, resolution, site_id)
    if min_val is None:
        msg = f"No default min/max values set for {var_col_name} range test"
        logger.error(msg)
        raise ValueError(msg)

    df = df.with_columns(
        pl.when(pl.col(var_col_name).lt(min_val) | pl.col(var_col_name).gt(max_val))
        .then(pl.col(flag_col_name) + 64)
        .otherwise(pl.col(flag_col_name))
        .alias(flag_col_name)
    )

    return df


def battery_voltage_test(df: pl.DataFrame, var_col_name: str, flag_col_name: str, site_id: str) -> pl.DataFrame:
    """
    Test the battery voltage level is above the threshold.

    This function checks if the battery voltage ('BATTV' column) is below a certain threshold
    and applies a quality control flag to the specified column if it is.

    Args:
        df: The input DataFrame containing the data to be tested.
        var_col_name: The name of the column to which the quality control will be applied.
        flag_col_name: The name of the column to which the quality control flags will be added.
        site_id: Site identifier

    Returns:
        pl.DataFrame: The DataFrame with the quality control flag applied, or returned as is if
        the 'BATTV' column is not present in the input DataFrame.
    """
    if "BATTV" not in df:
        logger.warning("Can not run Battery voltage test. No BATTV data provided")
        return df
    else:
        battv_config = qc_config.get_qc_config("battv_threshold")

        flags = col_comparison_test(df.select(var_col_name), df["BATTV"], battv_config.threshold, flag=5, op="<")

        return add_qcflag_column(df, flags, var_col_name)


def soilmet_scans_test(df: pl.DataFrame, var_col_name: str, flag_col_name: str, site_id: str) -> pl.DataFrame:
    """
    Test the soilmet scans value is above the threshold.

    This function checks if the soilmet scans value ('SCANS' column)
    is below a certain threshold and applies a quality control flag to
    the appropriate columns if it is.

    Args:
        df: The input DataFrame containing the data to be tested.
        var_col_name: The name of the column to which the quality control will be applied.
        flag_col_name: The name of the column to which the quality control flags will be added.
        site_id: Site identifier

    Returns:
        pl.DataFrame: The DataFrame with the quality control flag
        applied, or returned as is if the 'BATTV' column is not
        present in the input DataFrame.
    """
    if "SCANS" not in df:
        logger.warning("Can not run soilmet scans test. No SCANS column in data.")
        return df
    else:
        soilmet_scan_config = qc_config.get_qc_config("soilmet_scan_threshold")

        flags = col_comparison_test(df.select(var_col_name), df["SCANS"], soilmet_scan_config.threshold, flag=5, op="<")

        return add_qcflag_column(df, flags, var_col_name)


def spike_test(df: pl.DataFrame, var_col_name: str, flag_col_name: str, site_id: str) -> pl.DataFrame:
    """
    Assess the total difference between a value and its neighbours and
    remove any skew in the size of the differences with each neighbour.

    Args:
        df: The input DataFrame containing the data to be tested.
        var_col_name: The name of the column to which the quality control will be applied.
        flag_col_name: The name of the column to which the quality control flags will be added.
        site_id: Site identifier

    Returns:
        pl.DataFrame: The DataFrame with the quality control flag applied.
    """
    # Place holder. We need to pass in the data resolution. As is, this means this test will
    # only work for 30min data.
    resolution = "PT30M"

    spike_configs = qc_config.get_qc_config("spike_thresholds")
    spike_config = spike_configs.get(var_col_name)
    if spike_config is None:
        logger.warning(f"Can not run spike test. No {var_col_name} data provided")
        return df

    thres = get_spike_threshold(spike_config, resolution, site_id)
    if thres is None:
        msg = f"No default threshold set for {var_col_name} spike test"
        logger.error(msg)
        raise ValueError(msg)

    # Make a new dataframe for doing data shifting
    tst_spikes = df.clone()

    # Difference between value and previous value
    tst_spikes = tst_spikes.with_columns(pl.col(var_col_name).shift(1).alias("prev_val"))
    tst_spikes = tst_spikes.with_columns((pl.col(var_col_name) - pl.col("prev_val")).alias("diff_prev"))

    # Difference between next value and value
    tst_spikes = tst_spikes.with_columns(pl.col(var_col_name).shift(-1).alias("next_val"))
    tst_spikes = tst_spikes.with_columns((pl.col("next_val") - pl.col(var_col_name)).alias("diff_next"))

    # Calculate overall combined difference, absolute value
    tst_spikes = tst_spikes.with_columns((pl.col("diff_prev") - pl.col("diff_next")).abs().alias("d"))

    # Calulate the absolute skew in differences each side of the data
    # value.
    tst_spikes = tst_spikes.with_columns((pl.col("diff_prev").abs() - pl.col("diff_next").abs()).abs().alias("skew"))

    # Calculate the total difference minus the skew
    tst_spikes = tst_spikes.with_columns((pl.col("d") - pl.col("skew")).alias("d_no_skew"))

    # As we have summed the differences, we should double the threshold
    spikes = tst_spikes["d_no_skew"] > (thres * 2.0)

    df = df.with_columns(
        pl.when(spikes).then(pl.col(flag_col_name) + 512).otherwise(pl.col(flag_col_name)).alias(flag_col_name)
    )

    return df


# Map method IDs to function
qc_test_map = {
    "BATTV": battery_voltage_test,
    "RANGE": range_test,
    "SCANS": soilmet_scans_test,
    "SPIKE": spike_test,
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
        if test_id in qc_test_map:
            test_func = qc_test_map.get(test_id)
        else:
            logger.warning(f"No QC function available for {test_info.test_name}")
            continue

        for variable in test_info.variables:
            if variable in df.columns:
                logger.info(f"QC TEST: {test_info.test_name}. Running for: {variable}")
            else:
                logger.warning(f"QC TEST: {test_info.test_name}. {variable} doesnt exist in dataframe.")
                continue

            flag_col_name = create_flag_column_name(variable)
            if flag_col_name not in df:
                # Add flag column, initially with all 0's
                df = df.with_columns(pl.lit(0).alias(flag_col_name))

            site_ids = df.get_column("SITE_ID").unique()
            site_dfs = []
            for site_id in site_ids:
                site_df = df.filter(pl.col("SITE_ID") == site_id).select("time", "SITE_ID", variable, flag_col_name)
                # Run the QC test
                site_dfs.append(test_func(site_df, variable, flag_col_name, site_id))

            all_site_flags = pl.concat(site_dfs).drop(variable)

            # Replace previous QCFLAG column with new data.
            # Perform a join on 'time' and 'SITE_ID' to make sure data are saved in
            # correct rows.
            df = df.join(all_site_flags, on=["time", "SITE_ID"], how="left", suffix="_new")
            # Drop the extra original column
            df = df.drop(f"{flag_col_name}")
            # Rename
            df = df.rename({f"{flag_col_name}_new": flag_col_name})

    return df
