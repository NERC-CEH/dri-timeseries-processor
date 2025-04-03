from typing import Union

import polars as pl
from time_stream import Period

from dritimeseriesprocessor.deriving.calculation import Calculation


class HpaToKpa(Calculation):
    def __init__(self, col: Union[str, pl.Expr], column_name: str = None):
        """Convert hPa to kPa.

        Args:
            col: Name of column to convert with hPa units
            column_name: Custom name for the output column. If None, will be set to the class default.
        """
        from_units, to_units = "hPa", "kPa"
        super().__init__(f"Conversion from {from_units} to {to_units}", column_name, to_units)
        self._col = self._columns_to_expressions(col)

    @property
    def default_column_name(self) -> str:
        return self._col.meta.output_name()

    def expr(self) -> pl.Expr:
        kpa = self._col * 0.1
        return kpa


class WattsToMegajoules(Calculation):
    def __init__(self, col: Union[str, pl.Expr], period: Period, column_name: str = None):
        """Convert Watts to Megajoules per time period.

        # 1 Watt = 1 Joule per second
        # 1 Megajoule = 1,000,000 Joules
        # Therefore conversion factor is number of seconds in period, divided by 1,000,000

        Args:
            col: Name of column to convert with Watts units
            period: Period of observation
            column_name: Custom name for the output column. If None, will be set to the class default.
        """
        if period.timedelta is None:
            raise ValueError("Time period cannot be month-based.")
        self._period = period

        from_units, to_units = "W", "MJ"
        super().__init__(f"Conversion from {from_units} to {to_units}", column_name, to_units)
        self._col = self._columns_to_expressions(col)

    @property
    def default_column_name(self) -> str:
        return self._col.meta.output_name()

    def expr(self) -> pl.Expr:
        period_seconds = self._period.timedelta.total_seconds()
        mj = self._col * (period_seconds / 1e6)
        return mj
