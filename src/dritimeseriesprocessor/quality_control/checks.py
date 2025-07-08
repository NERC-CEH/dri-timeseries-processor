import logging
import sys
from datetime import time
from typing import List

import polars as pl
from time_stream import TimeSeries

from dritimeseriesprocessor.quality_control.base import BaseCheck, DepTS

logger = logging.getLogger(__name__)


class BatteryVoltageCheck(BaseCheck):
    """Check that the battery voltage level is above the threshold."""

    fdri_param_aliases = {"dep_ts": "battv_col"}

    def __init__(self, qc_column: str, flag_column: str, flag_name: str, battv_col: str, lt: float) -> None:
        """Initialize the battery voltage check.

        Args:
            qc_column: The name of the column being quality controlled.
            flag_column: The column to which flag values should be added.
            flag_name: The name of the flag to be added.
            battv_col: The name of the battery voltage column to search for.
            lt: The minimum-acceptable battery voltage. Values below this will be flagged.
        """
        super().__init__(qc_column=qc_column, flag_column=flag_column, flag_name=flag_name)

        self.lt = lt
        self.battv_col = battv_col

    def _check_expression(self, ts: TimeSeries, dep_ts: DepTS = None) -> pl.Expr:
        """Create expression to check if battery voltage is below the threshold."""
        battv_ts = self._get_column_data(ts, self.battv_col, dep_ts)
        return self.get_threshold_expression(battv_ts, self.battv_col, self.lt, "<")


class RangeCheck(BaseCheck):
    """Check that values fall between minimum and maximum range limits.

    Min and max range values are defined per site, per variable and per time resolution.
    """

    def __init__(self, qc_column: str, flag_column: str, flag_name: str, gt: float, lt: float) -> None:
        """Initialize the range check.

        Args:
            qc_column: The name of the column being quality controlled.
            flag_column: The column to which flag values should be added.
            flag_name: The name of the flag to be added.
            gt: The maximum acceptable value. Values above this will be flagged.
            lt: The minimum acceptable value. Values below this will be flagged.
        """
        super().__init__(qc_column=qc_column, flag_column=flag_column, flag_name=flag_name)
        self.gt = gt
        self.lt = lt

    def _check_expression(self, ts: TimeSeries, dep_ts: DepTS = None) -> pl.Expr:
        """Create expression to check if values fall outside the acceptable range."""
        return (pl.col(self.qc_column) < self.lt) | (pl.col(self.qc_column) > self.gt)


class SoilmetScansCheck(BaseCheck):
    """Check that the soilmet scan count is above an acceptable threshold."""

    def __init__(self, qc_column: str, flag_column: str, flag_name: str, scans_col: str, lt: float) -> None:
        """Initialize the soilmet scans check.

        Args:
            qc_column: The name of the column being quality controlled.
            flag_column: The column to which flag values should be added.
            flag_name: The name of the flag to be added.
            scans_col: The name of the `scans` column to search for.
            lt: The minimum number of scans.
        """
        super().__init__(qc_column=qc_column, flag_column=flag_column, flag_name=flag_name)
        self.lt = lt
        self.scans_col = scans_col

    def _check_expression(self, ts: TimeSeries, dep_ts: DepTS = None) -> pl.Expr:
        """Create expression to check if scan count is below the threshold."""
        scans_ts = self._get_column_data(ts, self.scans_col, dep_ts)
        return self.get_threshold_expression(scans_ts, self.scans_col, self.lt, "<")


class SpikeCheck(BaseCheck):
    """Detect spikes by assessing differences with neighboring values."""

    def __init__(self, qc_column: str, flag_column: str, flag_name: str, gt: float) -> None:
        """Initialize the spike detection check.

        Args:
            qc_column: The name of the column being quality controlled.
            flag_column: The column to which flag values should be added.
            flag_name: The name of the flag to be added.
            gt: The spike threshold.
        """
        super().__init__(qc_column=qc_column, flag_column=flag_column, flag_name=flag_name)
        self.gt = gt

    def _check_expression(self, ts: TimeSeries, dep_ts: DepTS = None) -> pl.Expr:
        """Create expression for spike detection.

        The algorithm:
        1. Calculate the difference between current value and previous value
        2. Calculate the difference between next value and current value
        3. Compute total combined difference (absolute value)
        4. Calculate skew in differences on each side
        5. Subtract skew from total difference
        6. Flag values where (total_difference - skew) > threshold * 2
        """
        # Calculate differences with temporal neighbors
        prev_val = pl.col(self.qc_column).shift(1)
        next_val = pl.col(self.qc_column).shift(-1)

        diff_prev = pl.col(self.qc_column) - prev_val
        diff_next = next_val - pl.col(self.qc_column)

        # Calculate total difference and skew
        d = (diff_prev - diff_next).abs()
        skew = (diff_prev.abs() - diff_next.abs()).abs()
        d_no_skew = d - skew

        # As we have summed the differences, we should double the threshold
        return d_no_skew.gt(self.gt * 2.0)


class RadiometerTaCheck(BaseCheck):
    """Check radiometer temperature values against acceptable range limits.

    This check flags the main time series data when radiometer temperature from a dependent time series falls outside
    acceptable operating ranges, as extreme temperatures can affect radiometer measurement accuracy.
    """

    def __init__(self, qc_column: str, flag_column: str, flag_name: str, rad_col: str, gt: float, lt: float) -> None:
        """Initialize the radiometer temperature check.

        Args:
            qc_column: The name of the column being quality controlled.
            flag_column: The column to which flag values should be added.
            flag_name: The name of the flag to be added.
            rad_col: The name of the radiometer temperature column to search for.
            gt: The maximum acceptable temperature. Values above this will cause flagging.
            lt: The minimum acceptable temperature. Values below this will cause flagging.
        """
        super().__init__(qc_column=qc_column, flag_column=flag_column, flag_name=flag_name)
        self.gt = gt
        self.lt = lt
        self.rad_col = rad_col

    def _check_expression(self, ts: TimeSeries, dep_ts: DepTS = None) -> pl.Expr:
        """Create the expression to check if radiometer temperature is out of range."""
        rad_ts = self._get_column_data(ts, self.rad_col, dep_ts)

        # Create expression for values outside the range
        expr = (pl.col(self.rad_col) < self.lt) | (pl.col(self.rad_col) > self.gt)

        # Resolve against the TimeSeries containing the column
        return self._resolve_dependent_expression(rad_ts, expr)


class HeatFluxPlateCheck(BaseCheck):
    """Flag data during heat flux plate calibration heating periods, as these periods produce invalid
    measurement data."""

    def __init__(self, qc_column: str, flag_column: str, flag_name: str, time_ge: time, time_le: time) -> None:
        """Initialize the heat flux plate check.

        Args:
            qc_column: The name of the column being quality controlled.
            flag_column: The column to which flag values should be added.
            flag_name: The name of the flag to be added.
            time_ge: The minimum time to remove data from.
            time_le: The maximum time to remove data from.
        """
        super().__init__(qc_column=qc_column, flag_column=flag_column, flag_name=flag_name)
        self.time_ge = time_ge
        self.time_le = time_le

    def _check_expression(self, ts: TimeSeries, dep_ts: DepTS = None) -> pl.Expr:
        """Create expression to flag data during calibration heating periods."""
        return (pl.col(ts.time_name).dt.time() >= self.time_ge) & (pl.col(ts.time_name).dt.time() <= self.time_le)


class PluvioDiagnosticCheck(BaseCheck):
    """Check that pluvio precipitation gauge diagnostic values are within limits."""

    def __init__(self, qc_column: str, flag_column: str, flag_name: str, diagnostic_col: str, gt: float) -> None:
        """Initialize the pluvio diagnostic check.

        Args:
            qc_column: The name of the column being quality controlled.
            flag_column: The column to which flag values should be added.
            flag_name: The name of the flag to be added.
            diagnostic_col: The name of the pluvio diagnostic column to search for.
            gt: The maximum acceptable diagnostic value. Values above this will cause flagging.
        """
        super().__init__(qc_column=qc_column, flag_column=flag_column, flag_name=flag_name)
        self.gt = gt
        self.diagnostic_col = diagnostic_col

    def _check_expression(self, ts: TimeSeries, dep_ts: DepTS = None) -> pl.Expr:
        """Create expression to check if diagnostic values exceed the threshold."""
        diagnostic_ts = self._get_column_data(ts, self.diagnostic_col, dep_ts)
        expr = self.get_threshold_expression(diagnostic_ts, self.diagnostic_col, self.gt, ">")
        return expr


class SnowDistanceSignalCheck(BaseCheck):
    """Check that snow distance sensor signal strength is adequate."""

    def __init__(self, qc_column: str, flag_column: str, flag_name: str, signal_col: str, lt: float) -> None:
        """Initialize the snow distance signal check.

        Args:
            qc_column: The name of the column being quality controlled.
            flag_column: The column to which flag values should be added.
            flag_name: The name of the flag to be added.
            signal_col: The name of the snow sensor signal column to search for.
            lt: The minimum-acceptable signal strength. Values below this will cause flagging.
        """
        super().__init__(qc_column=qc_column, flag_column=flag_column, flag_name=flag_name)
        self.lt = lt
        self.signal_col = signal_col

    def _check_expression(self, ts: TimeSeries, dep_ts: DepTS = None) -> pl.Expr:
        """Create expression to check if signal values are below the threshold."""
        signal_ts = self._get_column_data(ts, self.signal_col, dep_ts)
        expr = self.get_threshold_expression(signal_ts, self.signal_col, self.lt, "<")
        return expr


class TDTSoilTempCheck(BaseCheck):
    """Check soil temperature for TDT sensors, flagging volumetric water content (VWC) readings when soil
    temperature from TDT sensors falls below acceptable levels, as low temperatures can affect the accuracy of
    VWC measurements.
    """

    def __init__(self, qc_column: str, flag_column: str, flag_name: str, soil_temp_col: str, lt: float) -> None:
        """Initialize the TDT soil temperature check.

        Args:
            qc_column: The name of the column being quality controlled.
            flag_column: The column to which flag values should be added.
            flag_name: The name of the flag to be added.
            soil_temp_col: The name of the TDT soil temperature column to search for.
            lt: The minimum-acceptable soil temperature.
        """
        super().__init__(qc_column=qc_column, flag_column=flag_column, flag_name=flag_name)
        self.lt = lt
        self.soil_temp_col = soil_temp_col

    def _check_expression(self, ts: TimeSeries, dep_ts: DepTS = None) -> pl.Expr:
        """Create the expression to check if soil temperature is below the threshold."""
        soil_temp_ts = self._get_column_data(ts, self.soil_temp_col, dep_ts)
        expr = self.get_threshold_expression(soil_temp_ts, self.soil_temp_col, self.lt, "<")
        return expr


class ErrorCodesCheck(BaseCheck):
    """Flag data based on specific error codes in the time series."""

    fdri_param_aliases = {"value": "error_codes"}

    def __init__(self, qc_column: str, flag_column: str, flag_name: str, error_codes: List[int | float | str]) -> None:
        """Initialize the error codes check.

        Args:
            qc_column: The name of the column being quality controlled.
            flag_column: The column to which flag values should be added.
            flag_name: The name of the flag to be added.
            error_codes: List of error codes to flag. Can be numeric or string values
                         depending on the data type of the time series.
        """
        super().__init__(qc_column=qc_column, flag_column=flag_column, flag_name=flag_name)
        self.error_codes = error_codes

    def _check_expression(self, ts: TimeSeries, dep_ts: DepTS = None) -> pl.Expr:
        """Create expression for error codes check."""
        # Check if the main column value is in the list of error codes
        return pl.col(self.qc_column).is_in(self.error_codes)


def get_qc_class(qc_class_name: str) -> type[BaseCheck]:
    """Return the QC class for a given QC class name.

    Args:
        qc_class_name: Name of the QC class to check.

    Returns:
        The QC class for a given QC class name.
    """
    module = sys.modules[__name__]
    cls = getattr(module, qc_class_name, None)
    if issubclass(cls, BaseCheck):
        return cls
    raise ValueError(f"No class named '{qc_class_name}' found in module '{__name__}'.")
