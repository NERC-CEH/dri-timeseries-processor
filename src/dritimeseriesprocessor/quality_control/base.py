from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, Optional, Union

import polars as pl
from time_stream import TimeSeries


class BaseCheck(ABC):
    """Base class for all quality control checks.

    This abstract base class provides common functionality for all QC checks, including
    - Dependent time series access
    - Flag application with automatic date filtering
    - Threshold expression creation utilities
    """

    def __init__(
        self,
        ts_ids: Dict[str, Dict[str, Union[str, TimeSeries]]],
        ts_id: str,
        flag_column: str,
        flag_name: str,
        observation_interval: tuple[datetime, Optional[datetime]],
    ) -> None:
        """Initialize the QC check with common parameters.

        Args:
            ts_ids: Dictionary mapping time series IDs to their metadata and data.
                   Structure: {ts_id: {"data": TimeSeries, ...}}
            ts_id: The ID of the main TimeSeries to check and apply flags to.
            flag_column: The column name in the TimeSeries where flags should be added.
            flag_name: The name/identifier of the flag to be added to the TimeSeries.
                      This corresponds to the method name in the QC config.
            observation_interval: Tuple of (start_date, end_date) defining the time period
                                 where this QC check should be applied. If end_date is None,
                                 the check applies from start_date to the end of the data.

        Raises:
            ValueError: If the specified ts_id is not found in ts_ids.
        """
        self.ts_ids = ts_ids
        self.ts_id = ts_id
        self.flag_column = flag_column
        self.flag_name = flag_name
        self.observation_interval = observation_interval

        # Validate that the time series exists
        if ts_id not in ts_ids:
            raise ValueError(f"TimeSeries '{ts_id}' not found in ts_ids.")

    @property
    def main_ts(self) -> TimeSeries:
        """Get the main time series being checked.

        Returns:
            TimeSeries: The main time series that will be checked and flagged.
        """
        return self.ts_ids[self.ts_id]["data"]

    def get_dependent_ts(self, dep_ts: str) -> TimeSeries:
        """Get a dependent time series with validation.

        Args:
            dep_ts: The ID of the dependent time series to retrieve.

        Returns:
            TimeSeries: The requested dependent time series.

        Raises:
            ValueError: If the specified dependent time series is not found.
        """
        if dep_ts not in self.ts_ids:
            raise ValueError(f"Dependent time series '{dep_ts}' not found in ts_ids.")
        return self.ts_ids[dep_ts]["data"]

    def get_date_filter(self, ts: TimeSeries) -> pl.Expr:
        """Get Polars expression for observation date interval filtering.

        Creates a boolean expression that is True for timestamps within the observation interval and False otherwise.

        Args:
            ts: The TimeSeries to create the filter for (used to get time column name).

        Returns:
            pl.Expr: Boolean polars expression for date filtering.
        """
        start_date, end_date = self.observation_interval
        if not end_date:
            end_date = pl.col(ts.time_name).max()
        return pl.col("time").is_between(start_date, end_date)

    @abstractmethod
    def check_expression(self) -> pl.Expr:
        """Create the boolean expression for the quality control check.

        This method must be implemented by each subclass to return a `Polars` expression that evaluates to True
        where data should be flagged as failing the quality control check.

        Returns:
            pl.Expr: Boolean expression indicating where to apply the QC flag.
                    True values will be flagged (within the observation interval).
        """
        pass

    @staticmethod
    def create_threshold_expression(
        check_ts: TimeSeries, threshold: float, operator: str, flag_na: bool = False
    ) -> pl.Expr:
        """Create a threshold comparison expression.
        Used for flagging one column of data, based on a threshold check of a different column

        For example, we could look at the battery voltage column (the "check_column"), compare it to a threshold
        using the given operator (e.g., which rows are < threshold), then the "flag_column" for any rows that are True
        for this check are flagged.

        Args:
            check_ts: The TimeSeries containing the column to check against the threshold.
            threshold: The threshold value for comparison.
            operator: Comparison operator as string. One of: '>', '>=', '<', '<=', '==', '!='.
            flag_na: If True, also flag NaN/null values as failing the check. Defaults to False.

        Returns:
            pl.Expr: Boolean expression that is True where the threshold check fails.

        Raises:
            KeyError: If an invalid operator is provided.
        """
        operator_map = {
            ">": pl.col(check_ts.column_name).gt(threshold),
            ">=": pl.col(check_ts.column_name).ge(threshold),
            "<": pl.col(check_ts.column_name).lt(threshold),
            "<=": pl.col(check_ts.column_name).le(threshold),
            "==": pl.col(check_ts.column_name).eq(threshold),
            "!=": pl.col(check_ts.column_name).ne(threshold),
        }

        if operator not in operator_map:
            raise KeyError(f"{operator} is an invalid operator, use: {', '.join(operator_map.keys())}")

        operator_expr = operator_map[operator]
        if flag_na:
            operator_expr = operator_expr | pl.col(check_ts.column_name).is_null()

        return operator_expr

    def resolve_dependent_expression(self, dep_ts: str, expr: pl.Expr) -> pl.Expr:
        """For checks that use a dependent time series, we need to resolve the expression against that TimeSeries
        data, as the dependent time series data is not available in the main TimeSeries obejct.

        Resolve into a Polars literal series, which acts as a boolean expression for the downstream flagging process.

        Args:
            dep_ts: The ID of the time series containing dependent data.
            expr: The Polars expression to resolve against dep_ts.

        Returns:
            pl.Expr: Literal boolean series of the resolved expression on the dependent time series data.
        """
        dep_ts = self.get_dependent_ts(dep_ts)
        return pl.lit(dep_ts.df.select(expr).to_series())

    def run(self) -> Dict[str, Dict[str, Union[str, TimeSeries]]]:
        """Execute the quality control check and return updated ts_ids.

        This method orchestrates the QC check by:
        1. Getting the check-specific boolean expression from subclass
        2. Applying observation interval date filtering
        3. Adding the flag to the main time series
        4. Updating the ts_ids dictionary

        Returns:
            Dict[str, Dict[str, Union[str, TimeSeries]]]: Updated ts_ids dictionary
            with flags applied to the main time series.
        """
        # Get the check-specific expression
        flag_expr = self.check_expression()

        # Apply observation interval filter
        date_filter = self.get_date_filter(self.main_ts)
        final_expr = flag_expr & date_filter

        # Add the flag
        self.main_ts.add_flag(self.flag_column, self.flag_name, final_expr)

        # Save the result back to the ts dictionary
        self.ts_ids[self.ts_id]["data"] = self.main_ts

        return self.ts_ids
