import logging
from typing import Dict, List

import polars as pl

from dritimeseriesprocessor.__metadata__.config_quality_control import get_qc_config

logger = logging.getLogger(__name__)


def column_threshold_check(
    df: pl.DataFrame,
    check_column: str,
    qc_column: str,
    threshold: float,
    operator: str,
    flag_id: int,
    flag_na: bool = False,
) -> pl.DataFrame:
    """Generic function for flagging one column of data, based on a threshold check of a different column

    For example, we could look at the battery voltage column (the "check_column"), compare it to a threshold
    using the given operator (e.g. which rows are < threshold), then the "qc_column" for any rows that are True for
    this check are flagged

    Args:
        df: This must have only the columns wanted for flagging
        check_column: The column of data that is being checked against the threshold
        qc_column: The column that should be flagged
        threshold: Threshold value
        operator: What comparison to make
        flag_id: The ID of the quality control flag that should be applied to data that fail this check.
        flag_na: Comparison tests against NaNs will always result in False. By default, NaN values will not cause
            data in data to be flagged. Set this to True to change that.

    Returns:
        DataFrame with flags applied to qc_column.
    """

    operator_map = {
        ">": pl.col(check_column).gt(threshold),
        ">=": pl.col(check_column).ge(threshold),
        "<": pl.col(check_column).lt(threshold),
        "<=": pl.col(check_column).le(threshold),
        "==": pl.col(check_column).eq(threshold),
        "!=": pl.col(check_column).ne(threshold),
    }

    if check_column not in df:
        raise UserWarning(f"Can not run column threshold check. No {check_column} data provided")

    if qc_column not in df:
        raise UserWarning(f"Can not run column threshold check. No {qc_column} data provided")

    if operator not in operator_map:
        raise ValueError(f"{operator} is an invalid operator, use: {', '.join(operator_map.keys())}")

    # Get the operator expression
    operator_expr = operator_map[operator]
    if flag_na:
        operator_expr = operator_expr | pl.col(check_column).is_null()

    # Apply the flags based on comparing requested column to the threshold
    df, flag_column = initialise_qc_column(df, qc_column)
    df = df.with_columns(
        pl.when(operator_expr).then(pl.col(flag_column).add(flag_id)).otherwise(pl.col(flag_column)).alias(flag_column)
    )

    return df


def get_site_range_values(site_id: str, variable: str, resolution: str) -> tuple[float, float]:
    """Get the site-specific minimum and maximum values for range check for a given site, column and resolution.

    This function searches through the site-specific range thresholds and returns the min and max values for
    a given site and resolution. If no specific values are found, it returns the default values for that column
    and resolution.

    Args:
        site_id: Site ID for which range values are needed
        variable: The variable name for which range values are needed
        resolution: The temporal resolution for which range values are needed

    Returns:
        A tuple containing the minimum and maximum values for the range check.
    """
    range_thresholds = get_qc_config("range_thresholds")
    range_threshold = range_thresholds.get(variable)
    if range_threshold is None:
        raise UserWarning(f"No {variable} range thresholds provided.")

    # Get the default values for the given resolution
    default_range_values = next(
        (
            range_thresh
            for range_thresh in range_threshold.defaults
            if range_thresh.resolutions is None or resolution in range_thresh.resolutions
        ),
        None,
    )

    # Get the site specific values for the given site and resolution, defaulting to default values if not found
    if range_threshold.sites:
        range_values = next(
            (
                range_thresh
                for range_thresh in range_threshold.sites
                if range_thresh.site_id == site_id
                and (range_thresh.resolutions is None or resolution in range_thresh.resolutions)
            ),
            default_range_values,
        )
    else:
        range_values = default_range_values

    if range_values is None:
        raise ValueError(f"No min/max values set for {variable} range test")

    return range_values.min_value, range_values.max_value


def initialise_qc_column(df: pl.DataFrame, column: str) -> tuple[pl.DataFrame, str]:
    """Initialise a QC flag column in the DataFrame if it doesn't already exist.

    Args:
        df: The DataFrame to operate on.
        column: The name of the column for which the QC flag column should be checked/created.

    Returns:
        A tuple containing the updated DataFrame and the name of the QC flag column.
    """
    if df.is_empty():
        raise UserWarning("Cannot initialise QC column on empty DataFrame")

    qc_column = f"{column}_QCFLAG"
    if qc_column not in df.columns:
        df = df.with_columns(
            pl.lit(0, dtype=pl.Int64).alias(qc_column)  # TODO: Get this 0 value from somewhere
        )
    return df, qc_column


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
