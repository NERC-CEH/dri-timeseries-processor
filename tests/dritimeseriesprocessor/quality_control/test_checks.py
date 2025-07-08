import unittest
from datetime import datetime, time

import polars as pl
from time_stream import TimeSeries

from dritimeseriesprocessor.quality_control.checks import (
    BatteryVoltageCheck, RangeCheck, SoilmetScansCheck, ErrorCodesCheck, SpikeCheck, RadiometerTaCheck,
    HeatFluxPlateCheck, PluvioDiagnosticCheck, SnowDistanceSignalCheck, TDTSoilTempCheck
)


class TestBatteryVoltageCheck(unittest.TestCase):
    def setUp(self):
        self.value_name = "value"
        self.flag_name = "battery_v"
        self.flag_col_name = f"{self.value_name}_QC_FLAG"

        times = [
            datetime(2023, 8, 10),
            datetime(2023, 8, 11),
            datetime(2023, 8, 12),
            datetime(2023, 8, 13),
            datetime(2023, 8, 14),
        ]

        self.battv_ts = TimeSeries(
            pl.DataFrame({'time': times, "BATTV": [12., 11., 9., 13., 8.]}),
            "time", metadata={"column_name": "BATTV"}
        )

        self.ts = TimeSeries(
            pl.DataFrame({'time': times, self.value_name: [1., 2., 3., 4., 5.]}),
            "time", metadata={"column_name": self.value_name}
        )
        self.ts.add_flag_system("qc_flags", {self.flag_name: 1})
        self.ts.init_flag_column("qc_flags", self.flag_col_name)

    def test_battery_voltage_below_threshold(self):
        """ Test that correct flags applied to values that match where BATTV is below threshold
        """
        check = BatteryVoltageCheck(
            self.value_name, self.flag_col_name, self.flag_name, self.battv_ts.column_name, lt=10.
        )
        result = check.run(self.ts, dep_ts=self.battv_ts)

        self.assertEqual(result.df[self.flag_col_name].to_list(), [0, 0, 1, 0, 1])

    def test_battery_voltage_none_below_threshold(self):
        """ Test that no flags applied because battery voltage all above threshold
        """
        check = BatteryVoltageCheck(
            self.value_name, self.flag_col_name, self.flag_name, self.battv_ts.column_name, lt=0.5
        )
        result = check.run(self.ts, dep_ts=self.battv_ts)

        self.assertEqual(result.df[self.flag_col_name].to_list(), [0, 0, 0, 0, 0])

    def test_battery_voltage_all_below_threshold(self):
        """ Test that flags applied to all values because battery voltage all below threshold
        """
        check = BatteryVoltageCheck(
            self.value_name, self.flag_col_name, self.flag_name, self.battv_ts.column_name, lt=100.
        )
        result = check.run(self.ts, dep_ts=self.battv_ts)

        self.assertEqual(result.df[self.flag_col_name].to_list(), [1, 1, 1, 1, 1])

    def test_battery_voltage_all_at_threshold(self):
        """ Test that no flags applied because battery voltage exactly at threshold
        """
        self.battv_ts.df = self.battv_ts.df.with_columns(pl.Series([10., 10., 10., 10., 10.]).alias("BATTV"))

        check = BatteryVoltageCheck(
            self.value_name, self.flag_col_name, self.flag_name, self.battv_ts.column_name, lt=10.
        )
        result = check.run(self.ts, dep_ts=self.battv_ts)

        self.assertEqual(result.df[self.flag_col_name].to_list(), [0, 0, 0, 0, 0])

    def test_no_battv_data(self):
        """ Test terror raised when 'BATTV' data is missing.
        """
        self.battv_ts.df = self.battv_ts.df.drop("BATTV")

        check = BatteryVoltageCheck(
            self.value_name, self.flag_col_name, self.flag_name, self.battv_ts.column_name, lt=10.
        )
        with self.assertRaises(UserWarning):
            check.run(self.ts, dep_ts=self.battv_ts)



class TestRangeCheck(unittest.TestCase):
    def setUp(self):
        self.value_name = "value"
        self.flag_name = "range"
        self.flag_col_name = f"{self.value_name}_QC_FLAG"

        times = [
            datetime(2023, 8, 10),
            datetime(2023, 8, 11),
            datetime(2023, 8, 12),
            datetime(2023, 8, 13),
            datetime(2023, 8, 14),
            datetime(2023, 8, 15),
        ]

        self.ts = TimeSeries(
            pl.DataFrame({'time': times, self.value_name: list(range(6))}),
            "time", metadata={"column_name": self.value_name}
        )
        self.ts.add_flag_system("qc_flags", {self.flag_name: 1})
        self.ts.init_flag_column("qc_flags", self.flag_col_name)

    def test_range_check(self):
        """ Test that the range check returns expected results when some values outside of range
        """
        check = RangeCheck(self.value_name, self.flag_col_name, self.flag_name, lt=0.5, gt=3.5)
        result = check.run(self.ts)
        self.assertEqual(result.df[self.flag_col_name].to_list(), [1, 0, 0, 0, 1, 1])

    def test_range_check_all_within(self):
        """ Test that the range check returns expected results when all values within range
        """
        check = RangeCheck(self.value_name, self.flag_col_name, self.flag_name, lt=-1., gt=10.)
        result = check.run(self.ts)
        self.assertEqual(result.df[self.flag_col_name].to_list(), [0, 0, 0, 0, 0, 0])

    def test_range_check_all_outside(self):
        """ Test that the range check returns expected results when all values within range
        """
        check = RangeCheck(self.value_name, self.flag_col_name, self.flag_name, lt=90., gt=100.)
        result = check.run(self.ts)
        self.assertEqual(result.df[self.flag_col_name].to_list(), [1, 1, 1, 1, 1, 1])

    def test_range_check_at_boundaries(self):
        """ Test that the range check returns expected results when values at boundaries
        """
        check = RangeCheck(self.value_name, self.flag_col_name, self.flag_name, lt=0., gt=5.)
        result = check.run(self.ts)
        self.assertEqual(result.df[self.flag_col_name].to_list(), [0, 0, 0, 0, 0, 0])


class TestSoilmetScansCheck(unittest.TestCase):
    def setUp(self):
        self.value_name = "value"
        self.flag_name = "samples"
        self.flag_col_name = f"{self.value_name}_QC_FLAG"

        times = [
            datetime(2023, 8, 10),
            datetime(2023, 8, 11),
            datetime(2023, 8, 12),
            datetime(2023, 8, 13),
            datetime(2023, 8, 14),
        ]

        self.scans_ts = TimeSeries(
            pl.DataFrame({'time': times, "SCANS": [20, 61, 100, 200, 59]}),
            "time", metadata={"column_name": "SCANS"}
        )

        self.ts = TimeSeries(
            pl.DataFrame({'time': times, self.value_name: list(range(5))}),
            "time", metadata={"column_name": self.value_name}
        )
        self.ts.add_flag_system("qc_flags", {self.flag_name: 1})
        self.ts.init_flag_column("qc_flags", self.flag_col_name)

    def test_scans_below_threshold(self):
        """ Test that correct flags applied to values that match where SCANS is below threshold
        """
        check = SoilmetScansCheck(
            self.value_name, self.flag_col_name, self.flag_name, self.scans_ts.column_name, lt=60.
        )
        result = check.run(self.ts, dep_ts=self.scans_ts)

        self.assertEqual(result.df[self.flag_col_name].to_list(), [1, 0, 0, 0, 1])

    def test_scans_none_below_threshold(self):
        """ Test that no flags applied because SCANS all above threshold
        """
        check = SoilmetScansCheck(
            self.value_name, self.flag_col_name, self.flag_name, self.scans_ts.column_name, lt=1.
        )
        result = check.run(self.ts, dep_ts=self.scans_ts)

        self.assertEqual(result.df[self.flag_col_name].to_list(), [0, 0, 0, 0, 0])

    def test_scans_all_below_threshold(self):
        """ Test that flags applied to all values because SCANS all below threshold
        """
        check = SoilmetScansCheck(
            self.value_name, self.flag_col_name, self.flag_name, self.scans_ts.column_name, lt=1000.
        )
        result = check.run(self.ts, dep_ts=self.scans_ts)

        self.assertEqual(result.df[self.flag_col_name].to_list(), [1, 1, 1, 1, 1])

    def test_scans_all_at_threshold(self):
        """ Test that no flags applied because SCANS exactly at threshold
        """
        self.scans_ts.df = self.scans_ts.df.with_columns(pl.Series([60., 60., 60., 60., 60.]).alias("SCANS"))
        check = SoilmetScansCheck(
            self.value_name, self.flag_col_name, self.flag_name, self.scans_ts.column_name, lt=60.
        )
        result = check.run(self.ts, dep_ts=self.scans_ts)

        self.assertEqual(result.df[self.flag_col_name].to_list(), [0, 0, 0, 0, 0])

    def test_no_scans_column(self):
        """ Test error raised when 'SCANS' column is missing.
        """
        self.scans_ts.df = self.scans_ts.df.drop("SCANS")

        check = SoilmetScansCheck(
            self.value_name, self.flag_col_name, self.flag_name, self.scans_ts.column_name, lt=60.
        )
        with self.assertRaises(UserWarning):
            check.run(self.ts, dep_ts=self.scans_ts)


class TestErrorCodesCheck(unittest.TestCase):
    """Test error_codes_qc function."""

    def setUp(self):
        self.value_name = "value"
        self.flag_name = "error_code"
        self.flag_col_name = f"{self.value_name}_QC_FLAG"

        times = [
            datetime(2023, 8, 10),
            datetime(2023, 8, 11),
            datetime(2023, 8, 12),
            datetime(2023, 8, 13),
            datetime(2023, 8, 14),
        ]

        self.ts = TimeSeries(
            pl.DataFrame({'time': times, self.value_name: [12.0, 8999, 9.8, 10.2, 7999]}),
            "time", metadata={"column_name": self.value_name}
        )
        self.ts.add_flag_system("qc_flags", {self.flag_name: 1})
        self.ts.init_flag_column("qc_flags", self.flag_col_name)

    def test_error_code_qc(self):
        """Test flag correctly raised if values equal the set error codes.
        """
        check = ErrorCodesCheck(self.value_name, self.flag_col_name, self.flag_name, error_codes=[8999, 7999])
        result = check.run(self.ts)
        self.assertEqual(result.df[self.flag_col_name].to_list(), [0, 1, 0, 0, 1])

    def test_error_code_no_error_codes(self):
        """Test flag ot set if no values equal the set error codes.
        """
        check = ErrorCodesCheck(self.value_name, self.flag_col_name, self.flag_name, error_codes=[0, 1])
        result = check.run(self.ts)
        self.assertEqual(result.df[self.flag_col_name].to_list(), [0, 0, 0, 0, 0])


class TestSpikeCheck(unittest.TestCase):
    def setUp(self):
        self.value_name = "value"
        self.flag_name = "spike"
        self.flag_col_name = f"{self.value_name}_QC_FLAG"

        times = [
            datetime(2023, 8, 10),
            datetime(2023, 8, 11),
            datetime(2023, 8, 12),
            datetime(2023, 8, 13),
            datetime(2023, 8, 14),
            datetime(2023, 8, 15),
        ]

        self.ts = TimeSeries(
            pl.DataFrame({'time': times, self.value_name: [1., 2., 3., 4., 5., 6.]}),
            "time", metadata={"column_name": self.value_name}
        )
        self.ts.add_flag_system("qc_flags", {self.flag_name: 1})
        self.ts.init_flag_column("qc_flags", self.flag_col_name)


    def test_basic_spike(self):
        """ Test that the spike check returns expected results for a simple spike in the data
        """
        self.ts.df = self.ts.df.with_columns(pl.Series([1., 2., 3., 40., 5., 6.]).alias(self.value_name))

        check = SpikeCheck(self.value_name, self.flag_col_name, self.flag_name, gt=10.)
        result = check.run(self.ts)
        self.assertEqual(result.df[self.flag_col_name].to_list(), [0, 0, 0, 1, 0, 0])

    def test_no_spike(self):
        """ Test that no flags are added for data with no spike
        """
        check = SpikeCheck(self.value_name, self.flag_col_name, self.flag_name, gt=10.)
        result = check.run(self.ts)
        self.assertEqual(result.df[self.flag_col_name].to_list(), [0, 0, 0, 0, 0, 0])

    def test_large_spike(self):
        """ Large spikes can cause the values around the spike to be flagged, if method not working correctly.
        Check this is not the case here.
        """
        self.ts.df = self.ts.df.with_columns(pl.Series([1., 999., 3., 4., 999999999., 6.]).alias(self.value_name))

        check = SpikeCheck(self.value_name, self.flag_col_name, self.flag_name, gt=10.)
        result = check.run(self.ts)
        self.assertEqual(result.df[self.flag_col_name].to_list(), [0, 1, 0, 0, 1, 0])


class TestRadiometerTaCheck(unittest.TestCase):
    def setUp(self):
        self.value_name = "lwin"
        self.flag_name = "nr01_temp"
        self.flag_col_name = f"{self.value_name}_QC_FLAG"

        times = [
            datetime(2023, 8, 10),
            datetime(2023, 8, 11),
            datetime(2023, 8, 12),
            datetime(2023, 8, 13),
            datetime(2023, 8, 14),
            datetime(2023, 8, 15),
        ]

        self.nr01_ts = TimeSeries(
            pl.DataFrame({'time': times, "nr01": list(range(6))}),
            "time", metadata={"column_name": "nr01"}
        )

        self.ts = TimeSeries(
            pl.DataFrame({'time': times, self.value_name: [2, 3, 4, 5, 4, 3]}),
            "time", metadata={"column_name": self.value_name}
        )
        self.ts.add_flag_system("qc_flags", {self.flag_name: 1})
        self.ts.init_flag_column("qc_flags", self.flag_col_name)


    def test_radiometer_temp_check(self):
        """ Test that the check returns expected results when some values outside of nr01 temp
        """
        check = RadiometerTaCheck(
            self.value_name, self.flag_col_name, self.flag_name, self.nr01_ts.column_name, gt=3.5, lt=0.5
        )
        result = check.run(self.ts, dep_ts=self.nr01_ts)
        self.assertEqual(result.df[self.flag_col_name].to_list(), [1, 0, 0, 0, 1, 1])

    def test_radiometer_temp_check_all_within(self):
        """ Test that the check returns expected results when all values within nr01 temp
        """
        check = RadiometerTaCheck(
            self.value_name, self.flag_col_name, self.flag_name, self.nr01_ts.column_name, gt=10., lt=-1.
        )
        result = check.run(self.ts, dep_ts=self.nr01_ts)
        self.assertEqual(result.df[self.flag_col_name].to_list(), [0, 0, 0, 0, 0, 0])

    def test_radiometer_temp_check_all_outside(self):
        """ Test that the check returns expected results when all values within nr01 temp
        """
        check = RadiometerTaCheck(
            self.value_name, self.flag_col_name, self.flag_name, self.nr01_ts.column_name, gt=100., lt=90.
        )
        result = check.run(self.ts, dep_ts=self.nr01_ts)
        self.assertEqual(result.df[self.flag_col_name].to_list(), [1, 1, 1, 1, 1, 1])

    def test_radiometer_temp_check_at_boundaries(self):
        """ Test that the check returns expected results when values at boundaries
        """
        check = RadiometerTaCheck(
            self.value_name, self.flag_col_name, self.flag_name, self.nr01_ts.column_name, gt=5., lt=0.
        )
        result = check.run(self.ts, dep_ts=self.nr01_ts)
        self.assertEqual(result.df[self.flag_col_name].to_list(), [0, 0, 0, 0, 0, 0])


class TestHeatFluxPlateCheck(unittest.TestCase):
    def setUp(self):
        self.value_name = "value"
        self.flag_name = "hfp_removal"
        self.flag_col_name = f"{self.value_name}_QC_FLAG"

        times = [
            datetime(2023, 8, 10, 0, 0),
            datetime(2023, 8, 10, 0, 30),
            datetime(2023, 8, 10, 1, 0),
            datetime(2023, 8, 10, 1, 30),
            datetime(2023, 8, 10, 2, 0),
            datetime(2023, 8, 10, 2, 30),
        ]

        self.ts = TimeSeries(
            pl.DataFrame({'time': times, self.value_name: list(range(6))}),
            "time", metadata={"column_name": self.value_name}
        )
        self.ts.add_flag_system("qc_flags", {self.flag_name: 1})
        self.ts.init_flag_column("qc_flags", self.flag_col_name)

    def test_hfp_removal_check(self):
        """ Test that the hfp removal check flags expected values within time range
        """
        check = HeatFluxPlateCheck(
            self.value_name, self.flag_col_name, self.flag_name, time_ge=time(0, 30), time_le=time(1, 30)
        )
        result = check.run(self.ts)
        self.assertEqual(result.df[self.flag_col_name].to_list(), [0, 1, 1, 1, 0, 0])

    def test_hfp_removal_check_all_within(self):
        """ Test that the hfp removal check flags all.
        """
        check = HeatFluxPlateCheck(
            self.value_name, self.flag_col_name, self.flag_name, time_ge=time(0, 0), time_le=time(4, 30)
        )
        result = check.run(self.ts)
        self.assertEqual(result.df[self.flag_col_name].to_list(), [1, 1, 1, 1, 1, 1])

    def test_hfp_removal_check_all_outside(self):
        """ Test that the hfp removal check flags none
        """
        check = HeatFluxPlateCheck(
            self.value_name, self.flag_col_name, self.flag_name, time_ge=time(5, 0), time_le=time(7, 30)
        )
        result = check.run(self.ts)
        self.assertEqual(result.df[self.flag_col_name].to_list(), [0, 0, 0, 0, 0, 0])


class TestPluvioDiagnosticCheck(unittest.TestCase):
    """Test pluvio_diagnostic_check function."""

    def setUp(self):
        self.value_name = "value"
        self.flag_name = "precip_diag"
        self.flag_col_name = f"{self.value_name}_QC_FLAG"

        times = [
            datetime(2023, 8, 10),
            datetime(2023, 8, 11),
            datetime(2023, 8, 12),
            datetime(2023, 8, 13),
            datetime(2023, 8, 14)
        ]

        self.precip_diag_ts = TimeSeries(
            pl.DataFrame({'time': times, "PRECIP_DIAG": [0., 0., 1., 20., -1]}),
            "time", metadata={"column_name": "PRECIP_DIAG"}
        )

        self.ts = TimeSeries(
            pl.DataFrame({'time': times, self.value_name: [1., 2., 3., 4., 5.]}),
            "time", metadata={"column_name": self.value_name}
        )
        self.ts.add_flag_system("qc_flags", {self.flag_name: 1})
        self.ts.init_flag_column("qc_flags", self.flag_col_name)

    def test_pluvio_diag_below_threshold(self):
        """ Test that correct flags applied to values that match where PRECIP_DIAG is above threshold
        """
        check = PluvioDiagnosticCheck(
            self.value_name, self.flag_col_name, self.flag_name, self.precip_diag_ts.column_name, gt=0.
        )
        result = check.run(self.ts, dep_ts=self.precip_diag_ts)
        self.assertEqual(result.df[self.flag_col_name].to_list(), [0, 0, 1, 1, 0])

    def test_pluvio_diag_none_below_threshold(self):
        """ Test that all flags applied because precip diag values all above threshold
        """
        check = PluvioDiagnosticCheck(
            self.value_name, self.flag_col_name, self.flag_name, self.precip_diag_ts.column_name, gt=-10.
        )
        result = check.run(self.ts, dep_ts=self.precip_diag_ts)
        self.assertEqual(result.df[self.flag_col_name].to_list(), [1, 1, 1, 1, 1])

    def test_pluvio_diag_all_below_threshold(self):
        """ Test that no flags applied to all values because precip diag values all below threshold
        """
        check = PluvioDiagnosticCheck(
            self.value_name, self.flag_col_name, self.flag_name, self.precip_diag_ts.column_name, gt=100.
        )
        result = check.run(self.ts, dep_ts=self.precip_diag_ts)
        self.assertEqual(result.df[self.flag_col_name].to_list(), [0, 0, 0, 0, 0])

    def test_no_precip_diag_column(self):
        """ Test terror raised when 'PRECIP_DIAG' column is missing.
        """
        self.precip_diag_ts.df = self.precip_diag_ts.df.drop("PRECIP_DIAG")

        check = PluvioDiagnosticCheck(
            self.value_name, self.flag_col_name, self.flag_name, self.precip_diag_ts.column_name, gt=10.
        )
        with self.assertRaises(UserWarning):
            check.run(self.ts, dep_ts=self.precip_diag_ts)


class TestSnowDistanceSignalCheck(unittest.TestCase):
    """Test snow_distance_signal_check function."""

    def setUp(self):
        self.value_name = "value"
        self.flag_name = "snowd_signal"
        self.flag_col_name = f"{self.value_name}_QC_FLAG"

        times = [
            datetime(2023, 8, 10),
            datetime(2023, 8, 11),
            datetime(2023, 8, 12),
            datetime(2023, 8, 13),
            datetime(2023, 8, 14)
        ]

        self.snow_ts = TimeSeries(
            pl.DataFrame({'time': times, "SNOWD_SIGNALQUALITY": [160., 170., 1., 20., -1]}),
            "time", metadata={"column_name": "SNOWD_SIGNALQUALITY"}
        )

        self.ts = TimeSeries(
            pl.DataFrame({'time': times, self.value_name: [1., 2., 3., 4., 5.]}),
            "time", metadata={"column_name": self.value_name}
        )
        self.ts.add_flag_system("qc_flags", {self.flag_name: 1})
        self.ts.init_flag_column("qc_flags", self.flag_col_name)

    def test_snowd_signal_below_threshold(self):
        """ Test that correct flags applied to values that match where SNOWD_SIGNALQUALITY is above threshold
        """
        check = SnowDistanceSignalCheck(
            self.value_name, self.flag_col_name, self.flag_name, self.snow_ts.column_name, lt=152.
        )
        result = check.run(self.ts, dep_ts=self.snow_ts)
        self.assertEqual(result.df[self.flag_col_name].to_list(), [0, 0, 1, 1,1])

    def test_snowd_signal_none_below_threshold(self):
        """ Test that no flags applied because snowd signal all above threshold
        """
        check = SnowDistanceSignalCheck(
            self.value_name, self.flag_col_name, self.flag_name, self.snow_ts.column_name, lt=-10.
        )
        result = check.run(self.ts, dep_ts=self.snow_ts)
        self.assertEqual(result.df[self.flag_col_name].to_list(), [0, 0, 0, 0, 0])

    def test_snowd_signal_all_below_threshold(self):
        """ Test that flags applied to all values because snowd signal all below threshold
        """
        check = SnowDistanceSignalCheck(
            self.value_name, self.flag_col_name, self.flag_name, self.snow_ts.column_name, lt=300.
        )
        result = check.run(self.ts, dep_ts=self.snow_ts)
        self.assertEqual(result.df[self.flag_col_name].to_list(), [1, 1, 1, 1, 1])

    def test_no_snowd_signal_column(self):
        """ Test terror raised when 'SNOWD_SIGNALQUALITY' column is missing.
        """
        self.snow_ts.df = self.snow_ts.df.drop("SNOWD_SIGNALQUALITY")

        check = SnowDistanceSignalCheck(
            self.value_name, self.flag_col_name, self.flag_name, self.snow_ts.column_name, lt=0.
        )
        with self.assertRaises(UserWarning):
            check.run(self.ts, dep_ts=self.snow_ts)


class TestTDTSoilTempCheck(unittest.TestCase):
    """Test tdt_soil_temp_check function."""

    def setUp(self):
        self.value_name = "TDT1_VWC"
        self.flag_name = "tdt_tsoil"
        self.flag_col_name = f"{self.value_name}_QC_FLAG"

        times = [
            datetime(2023, 8, 10),
            datetime(2023, 8, 11),
            datetime(2023, 8, 12),
            datetime(2023, 8, 13),
            datetime(2023, 8, 14)
        ]

        self.ts = TimeSeries(
            pl.DataFrame({'time': times, self.value_name: [41., 52., 43., 54., 45.]}),
            "time", metadata={"column_name": self.value_name}
        )

        self.soil_temp_ts = TimeSeries(
            pl.DataFrame({'time': times, "TDT1_TSOIL": [0.1, 0.5, 1., 1.5, 2.1]}),
            "time", metadata={"column_name": "TDT1_TSOIL"}
        )
        self.ts.add_flag_system("qc_flags", {self.flag_name: 1})
        self.ts.init_flag_column("qc_flags", self.flag_col_name)

    def test_tdt_tsoil_below_threshold(self):
        """ Test that correct flags applied to values that match where TDT1_TSOIL is above threshold
        """
        check = TDTSoilTempCheck(
            self.value_name, self.flag_col_name, self.flag_name, self.soil_temp_ts.column_name, lt=1.
        )
        result = check.run(self.ts, dep_ts=self.soil_temp_ts)
        self.assertEqual(result.df[self.flag_col_name].to_list(), [1, 1, 0, 0, 0])

    def test_tdt_tsoil_none_below_threshold(self):
        """ Test that no flags applied because tsoil all above threshold
        """
        check = TDTSoilTempCheck(
            self.value_name, self.flag_col_name, self.flag_name, self.soil_temp_ts.column_name, lt=0.
        )
        result = check.run(self.ts, dep_ts=self.soil_temp_ts)
        self.assertEqual(result.df[self.flag_col_name].to_list(), [0, 0, 0, 0, 0])

    def test_tdt_tsoil_all_below_threshold(self):
        """ Test that flags applied to all TDT1_VWCs because tsoil all below threshold
        """
        check = TDTSoilTempCheck(
            self.value_name, self.flag_col_name, self.flag_name, self.soil_temp_ts.column_name, lt=5.
        )
        result = check.run(self.ts, dep_ts=self.soil_temp_ts)
        self.assertEqual(result.df[self.flag_col_name].to_list(), [1, 1, 1, 1, 1])

    def test_no_precip_diag_column(self):
        """ Test terror raised when 'TDT1_TSOIL' column is missing.
        """
        self.soil_temp_ts.df = self.soil_temp_ts.df.drop("TDT1_TSOIL")

        check = TDTSoilTempCheck(
            self.value_name, self.flag_col_name, self.flag_name, self.soil_temp_ts.column_name, lt=0.
        )
        with self.assertRaises(UserWarning):
            check.run(self.ts, dep_ts=self.soil_temp_ts)
