"""Quality control helper functions."""

import logging
from typing import Dict, List, Optional, Tuple

import polars as pl

import dritimeseriesprocessor.__metadata__.config_quality_control as qc_config

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
        DataFrame with flags applied across all columns.
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
    flag_col = flag_col.cast(pl.Int64).replace(1, flag)

    # Apply the same flags to all columns in the given data
    flagged_data = data.with_columns([flag_col.alias(col) for col in data.columns])

    return flagged_data


def get_default_range_vals(
    range_threshold: qc_config.VariableRangeThresholds, resolution: str
) -> Tuple[Optional[float], Optional[float]]:
    """
    Get the default minimum and maximum values for a given resolution.

    This function searches through the default range thresholds and returns
    the min and max values based on the provided resolution. If no specific
    resolution is found, it returns the general default values.

    Args:
        range_threshold: The threshold object containing default values.
        resolution: The resolution for which the default range values are needed.

    Returns:
        Tuple[Optional[float], Optional[float]]:
        A tuple containing the minimum and maximum values. Returns
        (None, None) if no values are found.
    """
    min_val = None
    max_val = None

    # Establish defaults
    for range_thres_def in range_threshold.defaults:
        if range_thres_def.resolutions is None:
            # Default regardless of resolution
            min_val = range_thres_def.min_value
            max_val = range_thres_def.max_value

        elif resolution in range_thres_def.resolutions:
            # Defaults found for specific resolution
            min_val = range_thres_def.min_value
            max_val = range_thres_def.max_value
            break

    return min_val, max_val


def get_site_range_vals(
    range_threshold: qc_config.VariableRangeThresholds, site: str, resolution: str
) -> Tuple[Optional[float], Optional[float]]:
    """
    Get the site-specific minimum and maximum values for a given resolution.

    This function searches through the site-specific range thresholds and returns
    the min and max values for a given site and resolution. If no specific
    values are found, it returns (None, None).

    Args:
        range_threshold: The threshold object containing site-specific values.
        site: The site identifier for which range values are needed.
        resolution: The resolution for which the site-specific range values are needed.

    Returns:
        Tuple[Optional[float], Optional[float]]:
        A tuple containing the minimum and maximum values for the site. Returns
        (None, None) if no values are found.
    """
    min_val = None
    max_val = None

    if range_threshold.sites is not None:
        for range_thres_site in range_threshold.sites:
            if range_thres_site.site_id == site and (
                range_thres_site.resolutions is None or resolution in range_thres_site.resolutions
            ):
                min_val = range_thres_site.min_value
                max_val = range_thres_site.max_value
                break

    return min_val, max_val


def add_qcflag_column(df: pl.DataFrame, flags: pl.DataFrame, col_name: str) -> pl.DataFrame:
    """
    Create QC flag column.

    If a quality control flag column already exists for the specified column, the new
    flags are added to the existing ones. If no quality control flag column
    exists, a new column is appended to the DataFrame.

    Args:
        df: Dataframe to add flags to.
        flags: Flag data.
        col_name: Name of column which was tested.

    Returns:
        DataFrame with qc flag column.
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


def get_failed_qc_check_ids_from_flag(flag: int) -> List[int]:
    """Returns the indexes of failed tests from a QC flag

    Args:
        flag: The flag to calculate from.

    Returns: A list of indexes to failed QC checks.
    """

    return [1 << i for i, x in enumerate(reversed(bin(flag)[2:])) if x == "1"]


class QCTestIDValidator:
    """Validates that a list of QC tests is valid and non-wasteful

    These methods ensure that the test_id values are unique, bitwise,
    sequential, and don't skip any valid bits.

    It is desirable to not waste any bits, because maximum bits can grow
    quite large.

    These validation methods are currently only used in `pytest` to ensure
    that the QC check IDs are valid before changes are integrated."""

    @staticmethod
    def _check_id_type(id_value: int) -> None:
        """Checks the type of the test ID and raises a TypeError if
        not an integer.

        Args:
            id_value: A numberic value of the test ID.
        Raises:
            TypeError: Raises if type is not int.
        """

        if not isinstance(id_value, int):
            raise TypeError(f'A bitwise ID must be an integer, received "{type(id_value)}"')

    @staticmethod
    def _ids_are_unique(test_dict: Dict[str, dict]) -> bool:
        """Checks if IDs are unique

        Args:
            test_dict: A dictionary of dictionaries representing QC tests.

        Returns:
            bool: A bool result of whether the IDs are unique.
        """

        test_ids = [item["id"] for item in test_dict.values()]

        if len(test_ids) == len(set(test_ids)):
            return True

        return False

    @staticmethod
    def _ids_are_sequential(test_dict: Dict[str, dict]) -> bool:
        """Checks that IDs are sequential and start at number 1.

        Args:
            test_dict: A dictionary of dictionaries representing QC tests.

        Returns:
            bool: A bool result of whether the IDs are sequential and start at 1.
        """
        for i, test in enumerate(test_dict.values()):
            QCTestIDValidator._check_id_type(test["id"])

            if test["id"] != 1 << i:
                return False

        return True

    @staticmethod
    def _ids_are_bitwise(test_dict: Dict[str, dict]) -> bool:
        """Checks that all test IDs are bitwise.

        Args:
            test_dict: A dictionary of dictionaries representing QC tests.

        Returns:
            bool: A bool result of whether the IDs are bitwise.
        """

        for test in test_dict.values():
            QCTestIDValidator._check_id_type(test["id"])

            if test["id"] == 0 or ((test["id"] & (test["id"] - 1)) != 0):
                return False

        return True

    @staticmethod
    def _ids_are_all_present(test_dict: Dict[str, dict]) -> bool:
        """Checks that all tests have  a "test_id" attribute

        Args:
            test_dict: A dictionary of dictionaries representing QC tests.

        Returns:
            bool: A bool result of whether all tests have test IDs.
        """

        for test in test_dict.values():
            if "id" not in test:
                return False
            QCTestIDValidator._check_id_type(test["id"])

        return True

    @staticmethod
    def validate(test_dict: Dict[str, dict]) -> bool:
        """Checks that IDs in a list of tests are valid.

        Args:
            test_dict: A dictionary of dictionaries representing QC tests.

        Returns:
            bool: A bool result of whether the IDs are valid.
        """

        for check in [
            QCTestIDValidator._ids_are_unique,
            QCTestIDValidator._ids_are_bitwise,
            QCTestIDValidator._ids_are_sequential,
            QCTestIDValidator._ids_are_all_present,
        ]:
            if not check(test_dict):
                return False

        return True
