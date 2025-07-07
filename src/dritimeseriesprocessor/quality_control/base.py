import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Optional, Tuple

import polars as pl
from time_stream import TimeSeries

logger = logging.getLogger(__name__)

# Type alias for verbose dependent time series argument
DepTS = Optional[TimeSeries | List[TimeSeries]]


class BaseCheck(ABC):
    """Base class for all quality control checks.

    This abstract base class provides common functionality for all QC checks, including
    - Dependent time series access
    - Flag application with automatic date filtering
    - Threshold expression creation utilities
    """

    # Any custom aliases for parameter names from the FDRI metadata configuration items.
    fdri_param_aliases: dict[str, str] = {}

    def __init__(self, qc_column: str, flag_column: str, flag_name: str, **kwargs):
        """Initialize the QC check with common parameters.

        Args:
            qc_column: The name of the column being quality controlled.
            flag_column: The column name in the TimeSeries where flags should be added.
            flag_name: The name/identifier of the flag to be added to the TimeSeries.
            **kwargs: Any additional keyword arguments that the class needs
        """
        self.qc_column = qc_column
        self.flag_column = flag_column
        self.flag_name = flag_name

    @classmethod
    def from_fdri_params(cls, qc_column: str, flag_column: str, flag_name: str, params: dict) -> "BaseCheck":
        """Create a class object based on parameters expected from the FDRI metadata configuration items."""
        remapped = {cls.fdri_param_aliases.get(k, k): v for k, v in params.items()}
        return cls(qc_column, flag_column, flag_name, **remapped)

    @staticmethod
    def _get_date_filter(ts: TimeSeries, observation_interval: Tuple[datetime, Optional[datetime]] = None) -> pl.Expr:
        """Get Polars expression for observation date interval filtering.

        Creates a boolean expression that is True for timestamps within the observation interval and False otherwise.

        Args:
            ts: The TimeSeries to create the filter for (used to get time column name).
            observation_interval: Tuple of (start_date, end_date) defining the time period
                                 where this QC check should be applied. If end_date is None,
                                 the check applies from start_date to the end of the data.

        Returns:
            pl.Expr: Boolean polars expression for date filtering.
        """
        if not observation_interval:
            return pl.lit(True)

        start_date, end_date = observation_interval
        if not end_date:
            end_date = pl.col(ts.time_name).max()
        return pl.col(ts.time_name).is_between(start_date, end_date)

    @staticmethod
    def _get_column_data(ts: TimeSeries, column_name: str, dep_ts: DepTS = None) -> TimeSeries:
        """Find a column in the main or dependent TimeSeries.

        Args:
            ts: The main TimeSeries.
            column_name: The column name to search for.
            dep_ts: Optional list of dependent TimeSeries.

        Returns:
            Tuple of (TimeSeries containing the column, actual column name) or (None, None) if not found.
        """
        # First check if column exists in main TimeSeries
        if column_name in ts.df.columns:
            return ts

        # Then check dependent TimeSeries'
        if dep_ts:
            if isinstance(dep_ts, TimeSeries):
                dep_ts = [dep_ts]

            for dep_ts in dep_ts:
                if column_name in dep_ts.df.columns:
                    return dep_ts

        # If we get here, we haven't found a TimeSeries with that column name in...
        raise UserWarning(f"Column not found in main or dependent TimeSeries: {column_name}")

    def get_threshold_expression(
        self, ts: TimeSeries, column_name: str, threshold: float, operator: str, flag_na: bool = False
    ) -> pl.Expr:
        """Create a threshold comparison expression. Used for flagging one column of data, based on a threshold
        check of a different column.

        For example, we could look at the battery voltage column (the "check_column"), compare it to a threshold
        using the given operator (e.g., which rows are < the threshold), then the "flag_column" for any rows that are
        True for this check are flagged.

        Args:
            ts: The TimeSeries containing the column to check against the threshold.
            column_name: Which column in ts to compare against the threshold.
            threshold: The threshold value for comparison.
            operator: Comparison operator as string. One of: '>', '>=', '<', '<=', '==', '!='.
            flag_na: If True, also flag NaN/null values as failing the check. Defaults to False.

        Returns:
            pl.Expr: Boolean expression that is True where the threshold check fails.

        Raises:
            KeyError: If an invalid operator is provided.
        """
        if column_name not in ts.columns:
            raise KeyError(f"Invalid column name: '{column_name}', not found in TimeSeries.")

        operator_map = {
            ">": pl.col(column_name).gt(threshold),
            ">=": pl.col(column_name).ge(threshold),
            "<": pl.col(column_name).lt(threshold),
            "<=": pl.col(column_name).le(threshold),
            "==": pl.col(column_name).eq(threshold),
            "!=": pl.col(column_name).ne(threshold),
        }

        if operator not in operator_map:
            raise KeyError(f"{operator} is an invalid operator, use: {', '.join(operator_map.keys())}")

        operator_expr = operator_map[operator]
        if flag_na:
            operator_expr = operator_expr | pl.col(column_name).is_null()

        final_expr = self._resolve_dependent_expression(ts, operator_expr)
        return final_expr

    @staticmethod
    def _resolve_dependent_expression(dep_ts: TimeSeries, expr: pl.Expr) -> pl.Expr:
        """For checks that use a dependent time series, we need to resolve the expression against that TimeSeries
        data, as the dependent time series data is not available in the main TimeSeries object.

        Resolve into a `Polars` literal series, which acts as a boolean expression for the downstream flagging process.

        Args:
            dep_ts: The time series containing dependent data.
            expr: The `Polars` expression to resolve against dep_ts.

        Returns:
            pl.Expr: Literal boolean series of the resolved expression on the dependent time series data.
        """
        return pl.lit(dep_ts.df.select(expr).to_series())

    @abstractmethod
    def _check_expression(self, ts: TimeSeries, dep_ts: DepTS = None) -> pl.Expr:
        """Create the boolean expression for the quality control check.

        This method must be implemented by each subclass to return a `Polars` expression that evaluates to True
        where data should be flagged as failing the quality control check.

        Args:
            ts: The main TimeSeries to check and apply flags to.
            dep_ts: Any dependent TimeSeries' that the QC check will need data from.

        Returns:
            pl.Expr: Boolean expression indicating where to apply the QC flag.
                    True values will be flagged (within the observation interval).
        """
        pass

    def run(
        self, ts: TimeSeries, dep_ts: DepTS = None, observation_interval: Tuple[datetime, Optional[datetime]] = None
    ) -> TimeSeries:
        """Execute the quality control check and return updated ts_ids.

        This method orchestrates the QC check by:
        1. Getting the check-specific boolean expression from subclass
        2. Applying observation interval date filtering
        3. Adding the flag to the main time series

        Args:
            ts: The primary TimeSeries to check.
            dep_ts: Optional dependent TimeSeries needed for the check.
                          It can be a single TimeSeries or a list of TimeSeries.
            observation_interval: Tuple of (start_date, end_date) defining the time period
                                 where this QC check should be applied. If end_date is None,
                                 the check applies from start_date to the end of the data.

        Returns:
            TimeSeries: Updated TimeSeries object with QC flags applied.
        """
        if dep_ts is not None and isinstance(dep_ts, TimeSeries):
            dep_ts = [dep_ts]

        # Create the flag expression
        flag_expr = self._check_expression(ts, dep_ts)

        # Apply observation interval filter if specified
        date_filter = self._get_date_filter(ts, observation_interval)
        final_expr = flag_expr & date_filter

        # Add the flag
        ts.add_flag(self.flag_column, self.flag_name, final_expr)

        return ts
