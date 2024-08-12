import logging

import polars as pl

import dritimeseriesprocessor.config_quality_control as qc_config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


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
        data - DataFrame:
            This must have only the columns wanted for flagging

        test_col - Series:
            The column of data that determines which rows get flagged

        threshold - float:
            Threshold value

        flag - int:
            The flag value used

        op - str:
            What comparison to make, see operator_map.

        flag_na - bool:
            Comparison tests against NaNs will always result in False.
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


def battery_voltage_test(df, column):
    """Test the battery voltage level is above threshold"""
    if "BATTV" not in df:
        logger.warning("Can not run Battery voltage test. No BATTV data provided")
        return

    power_flags = col_comparison_test(df.select(column), df["BATTV"], qc_config.battv_voltage_threshold, flag=5, op="<")

    power_flags = power_flags.rename({column: f"{column}_QCFLAG"})

    flag_col_name = f"{column}_QCFLAG"
    power_flags = power_flags.rename({column: flag_col_name})

    if flag_col_name in df:
        # Add flag values onto existing values
        df = df.with_columns(
            pl.col(flag_col_name) + power_flags[flag_col_name]
        )
    else:
        # Append new column
        df = df.hstack(power_flags)

    return df


# Map method IDs to function
qc_test_map = {"BATTV": battery_voltage_test}


def run_qc(df):
    """ """
    var_test_map = qc_config.get_qc_config("variable_test_map")
    var_ranges = qc_config.get_qc_config("range_thresholds")

    for var_test in var_test_map:
        if var_test.variable_id not in df:
            continue

        for test in var_test.tests:
            test_func = qc_test_map.get(test)
            if test_func is None:
                logger.warning(f"No QC function available for {test}")
                continue

            df = test_func(df, var_test.variable_id)
