import logging
from abc import ABC, abstractmethod
from typing import ClassVar, Type

import polars as pl
from time_stream import TimeSeries

logger = logging.getLogger(__name__)

# Registry for built-in operations
_OP_REGISTRY = {}


def register_operation(cls: Type["Operation"]) -> Type["Operation"]:
    """Decorator to register operation classes using their name attribute.

    Args:
        cls: The operation class to register.

    Returns:
        The decorated class.
    """
    _OP_REGISTRY[cls.name] = cls
    return cls


class Operation(ABC):
    """Abstract base class for operations."""

    name: ClassVar[str]

    @abstractmethod
    def apply(
        self,
        ts: TimeSeries,
        date_filter: pl.Expr = pl.lit(True),
    ) -> "TimeSeries":
        """Apply the operation to the DataFrame within a TimeSeries object.

        Args:
            ts: The TimeSeries object containing the DataFrame to operate on.
            date_filter: Polars expression to filter dates on which to apply the operation.

        Returns:
            The modified TimeSeries object.
        """
        pass

    @classmethod
    def get(cls, operation: str, **kwargs) -> "Operation":
        """Factory method to get an operation instance from string names.

        Args:
            operation: The operation name, e.g. "multiply", "add", "power"
            **kwargs: Parameters specific to the operation type, used to initialise the class object.

        Returns:
            An instance of the appropriate Operation subclass.

        Raises:
            ValueError: If a string name is not registered as an operation.
        """
        if operation not in _OP_REGISTRY:
            raise ValueError(f"Unknown operation: {operation}. Available: {list(_OP_REGISTRY)}")
        return _OP_REGISTRY[operation](**kwargs)


@register_operation
class Multiply(Operation):
    """Multiply operation class."""

    name = "multiply"

    def __init__(self, correction_factor: float) -> None:
        """Initialise the Multiply operation with a correction factor.

        Args:
            correction_factor: The factor to multiply the column by.

        """
        self.correction_factor = correction_factor

    def apply(
        self,
        ts: TimeSeries,
        date_filter: pl.Expr = pl.lit(True),
    ) -> "TimeSeries":
        """Apply the multiply operation to the DataFrame within a TimeSeries object."""
        ts.df = ts.df.with_columns(
            pl.when(date_filter)
            .then(pl.col(ts.column_name) * self.correction_factor)
            .otherwise(pl.col(ts.column_name))
            .alias(ts.column_name)
        )
        return ts


@register_operation
class Add(Operation):
    """Add operation class."""

    name = "add"

    def __init__(self, correction_factor: float) -> None:
        """Initialise the Add operation with a correction factor.

        Args:
            correction_factor: The factor to add to the column.

        """
        self.correction_factor = correction_factor

    def apply(
        self,
        ts: TimeSeries,
        date_filter: pl.Expr = pl.lit(True),
    ) -> "TimeSeries":
        """Apply the add operation to the DataFrame within a TimeSeries object."""
        ts.df = ts.df.with_columns(
            pl.when(date_filter)
            .then(pl.col(ts.column_name) + self.correction_factor)
            .otherwise(pl.col(ts.column_name))
            .alias(ts.column_name)
        )
        return ts


@register_operation
class Power(Operation):
    """Power operation class."""

    name = "power"

    def __init__(self, correction_factor: int) -> None:
        """Initialise the Power operation with a correction factor.

        Args:
            correction_factor: The factor to raise the column to the power of.

        """
        self.correction_factor = correction_factor

    def apply(
        self,
        ts: TimeSeries,
        date_filter: pl.Expr = pl.lit(True),
    ) -> "TimeSeries":
        """Apply the power operation to the DataFrame within a TimeSeries object."""
        ts.df = ts.df.with_columns(
            pl.when(date_filter)
            .then(pl.col(ts.column_name).pow(self.correction_factor))
            .otherwise(pl.col(ts.column_name))
            .alias(ts.column_name)
        )
        return ts


@register_operation
class LWCorrection(Operation):
    """Long wave correction operation class."""

    name = "lw_corr"

    def __init__(self, lw_unc: TimeSeries, ta: TimeSeries, correction_factor: float) -> None:
        """Initialise the LW correction operation.

        Args:
            lw_unc: The TimeSeries object containing the uncalibrated long wave radiation data.
            ta: The TimeSeries object containing the air temperature data.
            correction_factor: The factor to multiply the uncalibrated long wave radiation by before re-calibration.

        """
        self.lw_unc = lw_unc
        self.ta = ta
        self.correction_factor = correction_factor

    def apply(
        self,
        ts: TimeSeries,
        date_filter: pl.Expr = pl.lit(True),
    ) -> "TimeSeries":
        """Apply the LW correction to the DataFrame within a TimeSeries object."""
        # First correct the uncalibrated values with the scalar correction.
        lw_unc_corr = self.lw_unc.df.with_columns(
            pl.when(date_filter)
            .then(pl.col(self.lw_unc.column_name) * self.correction_factor)
            .otherwise(pl.col(self.lw_unc.column_name))
            .alias(self.lw_unc.column_name)
        )

        # Now re-calibrate LW value with temperature adjustment.
        # Convert temperature to Kelvin
        ta_k = self.ta.df.with_columns(
            pl.when(date_filter)
            .then(pl.col(self.ta.column_name) + 273.15)
            .otherwise(pl.col(self.ta.column_name))
            .alias(self.ta.column_name)
        )

        # Get adjustment amount from Stefan-Boltzmann constant 5.67 * 10^-8
        sb_adj = ta_k.with_columns((pl.col(self.ta.column_name).pow(4) * 5.67 * 1e-8).alias("SB_adj")).select("SB_adj")

        # Recalculate LW value
        ts.df = ts.df.with_columns(
            pl.when(date_filter)
            .then((lw_unc_corr[self.lw_unc.column_name] + sb_adj["SB_adj"]).round(1))
            .otherwise(pl.col(ts.column_name))
            .alias(ts.column_name)
        )

        return ts


def pa(df: pl.DataFrame, column: str, correction_factor: float, mask: pl.Expr = pl.lit(True)) -> pl.DataFrame:
    """Placeholder for PA correction function"""
    return df


def wd(df: pl.DataFrame, column: str, correction_factor: float, mask: pl.Expr = pl.lit(True)) -> pl.DataFrame:
    """Placeholder for WD correction function"""
    return df
