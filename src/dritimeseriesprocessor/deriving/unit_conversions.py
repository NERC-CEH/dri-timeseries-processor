from abc import ABC, abstractmethod
from typing import Union

import polars as pl

from dritimeseriesprocessor.deriving.calculation import Calculation
from time_series import Period


class Conversion(Calculation, ABC):
    def __init__(self, col: Union[str, pl.Expr], column_name: str, from_units: str, to_units: str, reverse: bool):
        """Abstract base class for different types of units conversions, extending the Calculation class.

        Args:
            col: Name of column to convert.
            column_name: Custom name for the converted column. If None, will be set to the class default.
            from_units: Units of original value (in the non-reverse conversion).
            to_units: Units of converted value (in the non-reverse conversion).
            reverse: Whether to reverse the conversion.
        """
        self._col = self._columns_to_expressions(col)
        self._reverse = reverse

        from_units, to_units = self._determine_conversion(from_units, to_units)
        name = f"Conversion from {from_units} to {to_units}"

        super().__init__(name, column_name, to_units)

    @property
    def default_column_name(self) -> str:
        return self._col.meta.output_name()

    def _determine_conversion(self, from_units: str, to_units: str) -> tuple:
        """Flip the from and to units around if user wants to do the reverse conversion

        Args:
            from_units: Units of original value (in the non-reverse conversion).
            to_units: Units of converted value (in the non-reverse conversion).

        Returns:
            Tuple of from_units and to_units
        """
        if self._reverse:
            from_units, to_units = to_units, from_units
        return from_units, to_units

    def expr(self) -> pl.Expr:
        """Choice of _expr or _rexpr, depending on the "reverse" class attribute."""
        if not self._reverse:
            return self._expr()
        else:
            return self._rexpr()

    @abstractmethod
    def _expr(self) -> pl.Expr:
        """Polars expression representing the conversion calculation."""
        pass

    @abstractmethod
    def _rexpr(self) -> pl.Expr:
        """Polars expression representing the reverse conversion calculation."""
        pass


class HpaToKpa(Conversion):
    def __init__(self, col: Union[str, pl.Expr], column_name: str = None, reverse: bool = False):
        """Convert hPa to kPa (or vice versa with "reverse").

        Args:
            col: Name of column to convert with hPa units
            column_name: Custom name for the output column. If None, will be set to the class default.
            reverse: Whether to reverse the conversion (i.e. kPa to hPa).
        """
        from_units, to_units = "hPa", "kPa"
        super().__init__(col, column_name, from_units, to_units, reverse=reverse)

    def _expr(self) -> pl.Expr:
        kpa = self._col * 0.1
        return kpa

    def _rexpr(self) -> pl.Expr:
        hpa = self._col / 0.1
        return hpa


class WattsToMegajoules(Conversion):
    def __init__(self, col: Union[str, pl.Expr], period: Period, column_name: str = None, reverse: bool = False):
        """Convert Watts to Megajoules per time period (or vice versa with "reverse").

        # 1 Watt = 1 Joule per second
        # 1 Megajoule = 1,000,000 Joules
        # Therefore conversion factor is number of seconds in period, divided by 1,000,000

        Args:
            col: Name of column to convert with Watts units
            period: Period of observation
            column_name: Custom name for the output column. If None, will be set to the class default.
            reverse: Whether to reverse the conversion (i.e. MJ to W).
        """
        if period.timedelta is None:
            raise ValueError("Time period cannot be month-based.")
        self._period = period

        from_units, to_units = "W", "MJ"
        super().__init__(col, column_name, from_units, to_units, reverse=reverse)

    def _expr(self) -> pl.Expr:
        period_seconds = self._period.timedelta.total_seconds()
        mj = self._col * (period_seconds / 1e6)
        return mj

    def _rexpr(self) -> pl.Expr:
        period_seconds = self._period.timedelta.total_seconds()
        w = self._col / (period_seconds / 1e6)
        return w
