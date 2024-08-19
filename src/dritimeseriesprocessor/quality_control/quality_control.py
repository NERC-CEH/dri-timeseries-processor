"""Running the quality control checks."""

import logging

import polars as pl

import dritimeseriesprocessor.__metadata__.config_quality_control as qc_config
import dritimeseriesprocessor.quality_control.checks as qc_checks

logger = logging.getLogger(__name__)


# Map method IDs to function
qc_test_map = {"BATTV": qc_checks.battery_voltage_qc, "RANGE": qc_checks.range_qc, "SCANS": qc_checks.soilmet_scans_qc}


def run_qc(df: pl.DataFrame) -> pl.DataFrame:
    """
    Run data through Quality Control (QC) tests.

    This function applies a series of quality control tests
    to the input DataFrame based on the qc configuration.

    Args:
        df: The input DataFrame containing the data to be quality controlled.

    Returns:
        The DataFrame with quality control flags applied.

    Notes:
        - QC details are extracted from the QC config.
        - Each QC test has variables to run against
        - Variables not present in the dataframe are skipped.
        - Tests without a function are skipped.
        - The dataframe is modified in-place by adding or updating the QC flag columns.
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
                logger.info(f"QC TEST: {test_info.test_name} for variable: {variable}")
                df = test_func(df, variable)
            else:
                logger.warning(f"{variable} doesnt exist in dataframe.")

    return df
