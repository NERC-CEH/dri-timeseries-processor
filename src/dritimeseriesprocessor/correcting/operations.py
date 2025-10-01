import logging
from abc import ABC, abstractmethod
from typing import ClassVar, Type

import polars as pl
import time_stream as ts

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
        tf: ts.TimeFrame,
        filter_expr: pl.Expr = pl.lit(True),
    ) -> "ts.TimeFrame":
        """Apply the operation to the DataFrame within a ts.TimeFrame object.

        Args:
            tf: The ts.TimeFrame object containing the DataFrame to operate on.
            filter_expr: Polars expression to filter when to apply the operation. Defaults to applying to all rows.

        Returns:
            The modified ts.TimeFrame object.
        """
        pass

    @classmethod
    def get(cls, operation: str, **kwargs) -> "Operation":
        """Factory method to get an operation instance from string names.

        Args:
            operation: The operation name, e.g. "scalar", "add", "power"
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
class Scalar(Operation):
    """Scalar operation class."""

    name = "scalar"

    def __init__(self, correction_factor: float) -> None:
        """Initialise the Scale operation with a correction factor.

        Args:
            correction_factor: The factor to scale the column by.

        """
        self.correction_factor = correction_factor

    def apply(
        self,
        tf: ts.TimeFrame,
        filter_expr: pl.Expr = pl.lit(True),
    ) -> ts.TimeFrame:
        """Apply the scalar operation to the DataFrame within a ts.TimeFrame object."""
        column_name = tf.metadata["column_name"]
        tf = tf.with_df(
            tf.df.with_columns(
                pl.when(filter_expr)
                .then(pl.col(column_name) * self.correction_factor)
                .otherwise(pl.col(column_name))
                .alias(column_name)
            )
        )
        return tf


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
        tf: ts.TimeFrame,
        filter_expr: pl.Expr = pl.lit(True),
    ) -> ts.TimeFrame:
        """Apply the add operation to the DataFrame within a ts.TimeFrame object."""
        column_name = tf.metadata["column_name"]
        tf = tf.with_df(
            tf.df.with_columns(
                pl.when(filter_expr)
                .then(pl.col(column_name) + self.correction_factor)
                .otherwise(pl.col(column_name))
                .alias(column_name)
            )
        )
        return tf


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
        tf: ts.TimeFrame,
        filter_expr: pl.Expr = pl.lit(True),
    ) -> ts.TimeFrame:
        """Apply the power operation to the DataFrame within a ts.TimeFrame object."""
        column_name = tf.metadata["column_name"]
        tf = tf.with_df(
            tf.df.with_columns(
                pl.when(filter_expr)
                .then(pl.col(column_name).pow(self.correction_factor))
                .otherwise(pl.col(column_name))
                .alias(column_name)
            )
        )
        return tf


@register_operation
class LWCorrection(Operation):
    """Long wave correction operation class."""

    name = "lw_corr"

    def __init__(self, lw_unc: ts.TimeFrame, ta: ts.TimeFrame, correction_factor: float) -> None:
        """Initialise the LW correction operation.

        Args:
            lw_unc: The ts.TimeFrame object containing the uncalibrated long wave radiation data.
            ta: The ts.TimeFrame object containing the air temperature data.
            correction_factor: The factor to multiply the uncalibrated long wave radiation by before re-calibration.

        """
        self.lw_unc = lw_unc
        self.ta = ta
        self.correction_factor = correction_factor

    def apply(
        self,
        tf: ts.TimeFrame,
        filter_expr: pl.Expr = pl.lit(True),
    ) -> ts.TimeFrame:
        """Apply the LW correction to the DataFrame within a ts.TimeFrame object."""
        # First correct the uncalibrated values with the scalar correction.
        lw_unc_corr = Scalar(self.correction_factor).apply(self.lw_unc, filter_expr).df

        # Now re-calibrate LW value with temperature adjustment.
        # Convert temperature to Kelvin
        ta_k = Add(273.15).apply(self.ta, filter_expr).df

        # Get adjustment amount from Stefan-Boltzmann constant 5.67 * 10^-8
        sb_adj = ta_k.with_columns(
            (pl.col(self.ta.metadata["column_name"]).pow(4) * 5.67 * 1e-8).alias("SB_adj")
        ).select("SB_adj")

        # Recalculate LW value
        lw_column_name = self.lw_unc.metadata["column_name"]
        column_name = tf.metadata["column_name"]
        tf = tf.with_df(
            tf.df.with_columns(
                pl.when(filter_expr)
                .then((lw_unc_corr[lw_column_name] + sb_adj["SB_adj"]))
                .otherwise(pl.col(column_name))
                .alias(column_name)
            )
        )

        return tf


# TODO: Implement site attribute fetching
@register_operation
class PACorrection(Operation):
    """Correct air pressure with bias calculated from mean sea level pressure."""

    name = "pa_corr"

    def __init__(self, ta: ts.TimeFrame, altitude: float, correction_factor: float) -> None:
        """Initialise the PA correction operation.

        Args:
            ta: ts.TimeFrame object containing the air temperature data.
            altitude: Site altitude in metres.
            correction_factor: The factor used in PA correction.

        """
        self.ta = ta
        self.altitude = altitude
        self.correction_factor = correction_factor

    def apply(
        self,
        tf: ts.TimeFrame,
        filter_expr: pl.Expr = pl.lit(True),
    ) -> ts.TimeFrame:
        """Apply the PA correction to the DataFrame within a ts.TimeFrame object."""
        # Using the MSLP to PA conversion factor, calculate the unqiue adjustments
        # for each PA value.
        ta_column_name = self.ta.metadata["column_name"]
        corrs = self.ta.df.with_columns(
            pl.when(filter_expr)
            .then(
                self.correction_factor
                * (1 - ((0.0065 * self.altitude) / (pl.col(ta_column_name) + (0.0065 * self.altitude) + 273.15)))
                ** 5.257
            )
            .otherwise(pl.col(ta_column_name))
            .alias("pa_corr")
        )

        column_name = tf.metadata["column_name"]
        tf = tf.with_df(
            tf.df.with_columns(
                pl.when(filter_expr)
                .then((pl.col(column_name) + corrs["pa_corr"]))
                .otherwise(pl.col(column_name))
                .alias(column_name)
            )
        )

        return tf


# TODO: Placeholder implementation, to be replaced with real WD correction logic
@register_operation
class WDCorrection(Operation):
    """Wind direction correction operation class."""

    name = "wd_corr"

    def __init__(self, ux: ts.TimeFrame, uy: ts.TimeFrame) -> None:
        """Initialise the WD correction operation.

        Args:
            ux: The ts.TimeFrame object containing the u-component of wind data.
            uy: The ts.TimeFrame object containing the y-component of wind data.

        """
        self.ux = ux
        self.uy = uy

    def apply(
        self,
        tf: ts.TimeFrame,
        filter_expr: pl.Expr = pl.lit(True),
    ) -> ts.TimeFrame:
        """Apply the WD correction to the DataFrame within a ts.TimeFrame object."""
        return tf
