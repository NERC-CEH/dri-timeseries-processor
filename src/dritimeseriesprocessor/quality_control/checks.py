import logging
from datetime import time
from typing import Dict, List, Union

import polars as pl
from time_stream import TimeSeries

from dritimeseriesprocessor.quality_control.base import BaseCheck

logger = logging.getLogger(__name__)


class BatteryVoltageCheck(BaseCheck):
    """Check that the battery voltage level is above the threshold."""

    def __init__(self, *args, lt: float, dep_ts: str, **kwargs) -> None:
        """Initialize the battery voltage check.

        Args:
            lt: The minimum-acceptable battery voltage. Values below this will be flagged.
            dep_ts: The ID of the time series containing battery voltage data.
        """
        super().__init__(*args, **kwargs)
        self.lt = lt
        self.dep_ts = dep_ts

    def check_expression(self) -> pl.Expr:
        """Create expression to check if battery voltage is below the threshold.

        Returns:
            pl.Expr: Boolean expression that is True where battery voltage < lt.
        """
        battv_ts = self.get_dependent_ts(self.dep_ts)
        return self.create_threshold_expression(battv_ts, self.lt, "<")


class RangeCheck(BaseCheck):
    """Check that values fall between minimum and maximum range limits.

    Min and max range values are defined per site, per variable and per time resolution.
    """

    def __init__(self, *args, gt: float, lt: float, **kwargs) -> None:
        """Initialize the range check.

        Args:
            gt: The maximum acceptable value. Values above this will be flagged.
            lt: The minimum acceptable value. Values below this will be flagged.
        """
        super().__init__(*args, **kwargs)
        self.gt = gt
        self.lt = lt

    def check_expression(self) -> pl.Expr:
        """Create expression to check if values fall outside the acceptable range.

        Returns:
            pl.Expr: Boolean expression that is True where value < lt OR value > gt.
        """
        return pl.col(self.main_ts.column_name).lt(self.lt) | pl.col(self.main_ts.column_name).gt(self.gt)


class SoilmetScansCheck(BaseCheck):
    """Check that the soilmet scan count is above an acceptable threshold."""

    def __init__(self, *args, lt: float, dep_ts: str, **kwargs) -> None:
        """Initialize the soilmet scans check.

        Args:
            lt: The minimum acceptable number of scans. Values below this will be flagged.
            dep_ts: The ID of the time series containing scan count data.
        """
        super().__init__(*args, **kwargs)
        self.lt = lt
        self.dep_ts = dep_ts

    def check_expression(self) -> pl.Expr:
        """Create expression to check if scan count is below the threshold.

        Returns:
            pl.Expr: Boolean expression that is True where scan_count < lt.
        """
        scans_ts = self.get_dependent_ts(self.dep_ts)
        return self.create_threshold_expression(scans_ts, self.lt, "<")


class ErrorCodesCheck(BaseCheck):
    """Flag data based on specific error codes in the time series."""

    def __init__(self, *args, value: List[Union[int, float, str]], **kwargs) -> None:
        """Initialize the error codes check.

        Args:
            value: List of error codes to flag. Can be numeric or string values
                  depending on the data type of the time series.
        """
        super().__init__(*args, **kwargs)
        self.error_codes = value

    def check_expression(self) -> pl.Expr:
        """Create expression to check for specific error codes.

        Returns:
            pl.Expr: Boolean expression that is True where the value matches
                    any of the specified error codes.
        """
        return pl.col(self.main_ts.column_name).is_in(self.error_codes)


class SpikeCheck(BaseCheck):
    """Detect and flag spike values in time series data.

    Assesses the total difference between a value and its neighbours and removes any skew in the size of the
    differences with each neighbour.

    Note that the first and last value in the timeseries cannot be assessed, as they don't have previous/next values to
    assess spike against.
    """

    def __init__(self, *args, gt: float, **kwargs) -> None:
        """Initialize the spike detection check.

        Args:
            gt: The minimum spike threshold
        """
        super().__init__(*args, **kwargs)
        self.gt = gt

    def check_expression(self) -> pl.Expr:
        """Create expression for spike detection.

        The algorithm:
        1. Calculate the difference between current value and previous value
        2. Calculate the difference between next value and current value
        3. Compute total combined difference (absolute value)
        4. Calculate skew in differences on each side
        5. Subtract skew from total difference
        6. Flag values where (total_difference - skew) > threshold * 2

        Returns:
            pl.Expr: Boolean expression that is True where spikes are detected.
        """
        # Calculate differences with temporal neighbors
        prev_val = pl.col(self.main_ts.column_name).shift(1)
        next_val = pl.col(self.main_ts.column_name).shift(-1)

        diff_prev = pl.col(self.main_ts.column_name) - prev_val
        diff_next = next_val - pl.col(self.main_ts.column_name)

        # Calculate total difference and skew
        d = (diff_prev - diff_next).abs()
        skew = (diff_prev.abs() - diff_next.abs()).abs()
        d_no_skew = d - skew

        # As we have summed the differences, we should double the threshold
        return d_no_skew.gt(self.gt * 2.0)


class RadiometerTACheck(BaseCheck):
    """Check radiometer temperature values against acceptable range limits.

    This check flags the main time series data when radiometer temperature from a dependent time series falls outside
    acceptable operating ranges, as extreme temperatures can affect radiometer measurement accuracy.
    """

    def __init__(self, *args, gt: float, lt: float, dep_ts: str, **kwargs) -> None:
        """Initialize the radiometer temperature check.

        Args:
            gt: The maximum acceptable temperature. Values above this will cause flagging.
            lt: The minimum acceptable temperature. Values below this will cause flagging.
            dep_ts: The ID of the time series containing radiometer temperature data
        """
        super().__init__(*args, **kwargs)
        self.gt = gt
        self.lt = lt
        self.dep_ts = dep_ts

    def check_expression(self) -> pl.Expr:
        """Create the expression to check if radiometer temperature is out of range.

        Returns:
            pl.Expr: Boolean expression that is True where temperature < lt OR temperature > gt.
        """
        dep_ts = self.get_dependent_ts(self.dep_ts)
        return pl.col(dep_ts.column_name).lt(self.lt) | pl.col(dep_ts.column_name).gt(self.gt)


class HeatFluxPlateCheck(BaseCheck):
    """Flag data during heat flux plate calibration heating periods, as these periods produce invalid
    measurement data."""

    def __init__(self, *args, time_ge: time, time_le: time, **kwargs) -> None:
        """Initialize the heat flux plate calibration check.

        Args:
            time_ge: The start time of the calibration period (inclusive).
                    For example, time(0, 30) for 00:30.
            time_le: The end time of the calibration period (inclusive).
                    For example, time(1, 0) for 01:00.
        """
        super().__init__(*args, **kwargs)
        self.time_ge = time_ge
        self.time_le = time_le

    def check_expression(self) -> pl.Expr:
        """Create expression to flag data during calibration heating periods.

        Returns:
            pl.Expr: Boolean expression that is True during the specified time range
                    (time_ge <= time_of_day <= time_le).
        """
        return (pl.col(self.main_ts.time_name).dt.time() >= self.time_ge) & (
            pl.col(self.main_ts.time_name).dt.time() <= self.time_le
        )


class PluvioDiagnosticCheck(BaseCheck):
    """Check that pluvio precipitation gauge diagnostic values are within limits."""

    def __init__(self, *args, gt: float, dep_ts: str, **kwargs) -> None:
        """Initialize the pluvio diagnostic check.

        Args:
            gt: The maximum acceptable diagnostic value. Values above this will cause flagging.
            dep_ts: The ID of the time series containing pluvio diagnostic data.
        """
        super().__init__(*args, **kwargs)
        self.gt = gt
        self.dep_ts = dep_ts

    def check_expression(self) -> pl.Expr:
        """Create expression to check if diagnostic values exceed the threshold.

        Returns:
            pl.Expr: Boolean expression that is True where diagnostic_value > gt.
        """
        dep_ts = self.get_dependent_ts(self.dep_ts)
        return self.create_threshold_expression(dep_ts, self.gt, ">")


class SnowDistanceSignalCheck(BaseCheck):
    """Check that snow distance sensor signal strength is adequate."""

    def __init__(self, *args, lt: float, dep_ts: str, **kwargs) -> None:
        """Initialize the snow distance signal check.

        Args:
            lt: The minimum-acceptable signal strength. Values below this will cause flagging.
            dep_ts: The ID of the time series containing snow sensor signal strength data.
        """
        super().__init__(*args, **kwargs)
        self.lt = lt
        self.dep_ts = dep_ts

    def check_expression(self) -> pl.Expr:
        """Create expression to check if signal values are below the threshold.

        Returns:
            pl.Expr: Boolean expression that is True where signal_strength < lt.
        """
        sig_ts = self.get_dependent_ts(self.dep_ts)
        return self.create_threshold_expression(sig_ts, self.lt, "<")


class TDTSoilTempCheck(BaseCheck):
    """Check soil temperature for TDT sensors, flagging volumetric water content (VWC) readings when soil
    temperature from TDT sensors falls below acceptable levels, as low temperatures can affect the accuracy of
    VWC measurements.
    """

    def __init__(self, *args, lt: float, dep_ts: str, **kwargs) -> None:
        """Initialize the TDT soil temperature check.

        Args:
            lt: The minimum acceptable soil temperature.
            dep_ts: The ID of the time series containing TDT soil temperature data.
        """
        super().__init__(*args, **kwargs)
        self.lt = lt
        self.dep_ts = dep_ts

    def check_expression(self) -> pl.Expr:
        """Create the expression to check if soil temperature is below the threshold.

        Returns:
            pl.Expr: Boolean expression that is True where soil_temperature < lt.
        """
        # TODO: Consider using alternative TDT sensors if primary soil temperature is not available or incorrect.
        tsoil_ts = self.get_dependent_ts(self.dep_ts)
        return self.create_threshold_expression(tsoil_ts, self.lt, "<")


class QCCheckFactory:
    """Factory for creating quality control check instances."""

    _check_classes = {
        "battery_voltage_check": BatteryVoltageCheck,
        "range_check": RangeCheck,
        "soilmet_scans_check": SoilmetScansCheck,
        "error_codes_check": ErrorCodesCheck,
        "spike_check": SpikeCheck,
        "radiometer_ta_check": RadiometerTACheck,
        "heat_flux_plate_check": HeatFluxPlateCheck,
        "pluvio_diagnostic_check": PluvioDiagnosticCheck,
        "snow_distance_signal_check": SnowDistanceSignalCheck,
        "tdt_soil_temp_check": TDTSoilTempCheck,
    }

    @classmethod
    def create_check(cls, check_name: str, **kwargs) -> BaseCheck:
        """Create a QC check instance by name.

        Args:
            check_name: The name of the QC check to create. Must be one of the
                       registered check names in _check_classes.
            **kwargs: Keyword arguments to pass to the check constructor.
                     All checks require: ts_ids, ts_id, flag_column, flag_name,
                     observation_interval, plus check-specific parameters.

        Returns:
            BaseCheck: An instance of the specified QC check class.

        Raises:
            ValueError: If check_name is not found in the registry.
        """
        if check_name not in cls._check_classes:
            available_checks = ", ".join(cls._check_classes.keys())
            raise ValueError(f"Unknown QC check: '{check_name}'. Available checks: {available_checks}")

        check_class = cls._check_classes[check_name]
        return check_class(**kwargs)


def run_qc_check(check_name: str, **kwargs) -> Dict[str, Dict[str, Union[str, TimeSeries]]]:
    """Run a QC check using the class-based approach.

    Args:
        check_name: The name of the QC check to run.
        **kwargs: All parameters required by the specific QC check.

    Returns:
        Dict[str, Dict[str, Union[str, TimeSeries]]]: Updated ts_ids dictionary with QC flags applied.
    """
    check_instance = QCCheckFactory.create_check(check_name, **kwargs)
    return check_instance.run()
