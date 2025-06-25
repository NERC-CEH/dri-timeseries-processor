import unittest
from datetime import datetime

import polars as pl
from time_stream import TimeSeries

from dritimeseriesprocessor.quality_control.checks import (battery_voltage_check, error_codes_check, range_check,
                                                           soilmet_scans_check, spike_check)


class TestBatteryVoltageCheck(unittest.TestCase):
    def setUp(self):
        self.flag_name = "battery_v"

        data = pl.DataFrame({
            'time': [
                datetime(2023, 8, 10),
                datetime(2023, 8, 11),
                datetime(2023, 8, 12),
                datetime(2023, 8, 13),
                datetime(2023, 8, 14),
            ],
            "value": [1., 2., 3., 4., 5.],
        })
        battv_data = pl.DataFrame({
            'time': [
                datetime(2023, 8, 10),
                datetime(2023, 8, 11),
                datetime(2023, 8, 12),
                datetime(2023, 8, 13),
                datetime(2023, 8, 14),
            ],
            "BATTV": [12., 11., 9., 13., 8.],
        })

        self.ts = TimeSeries(data, "time", metadata={"column_name": "value"})
        self.ts.add_flag_system("qc_flags", {self.flag_name: 1})
        self.ts.init_flag_column("qc_flags", "value_QC_FLAG")

        battv_ts = TimeSeries(battv_data, "time", metadata={"column_name": "BATTV"})

        self.value_ts_id = "site1_value"
        self.battv_ts_id = "site1_battv_raw"

        self.ts_ids = {
            self.value_ts_id: {
                "data": self.ts
            },
            self.battv_ts_id: {
                "data": battv_ts
            }
        }

    def test_battery_voltage_below_threshold(self):
        """ Test that correct flags applied to values that match where BATTV is below threshold
        """
        result = battery_voltage_check(self.ts_ids, self.value_ts_id, "value_QC_FLAG", self.flag_name, 10., self.battv_ts_id)
        self.assertEqual(result[self.value_ts_id]["data"].df['value_QC_FLAG'].to_list(), [0, 0, 1, 0, 1])

    def test_battery_voltage_none_below_threshold(self):
        """ Test that no flags applied because battery voltage all above threshold
        """
        result = battery_voltage_check(self.ts_ids, self.value_ts_id, "value_QC_FLAG", self.flag_name, 0.5, self.battv_ts_id)
        self.assertEqual(result[self.value_ts_id]["data"].df['value_QC_FLAG'].to_list(), [0, 0, 0, 0, 0])

    def test_battery_voltage_all_below_threshold(self):
        """ Test that flags applied to all values because battery voltage all below threshold
        """
        result = battery_voltage_check(self.ts_ids, self.value_ts_id, "value_QC_FLAG", self.flag_name, 100., self.battv_ts_id)
        self.assertEqual(result[self.value_ts_id]["data"].df['value_QC_FLAG'].to_list(), [1, 1, 1, 1, 1])

    def test_battery_voltage_all_at_threshold(self):
        """ Test that no flags applied because battery voltage exactly at threshold
        """
        self.ts_ids[self.battv_ts_id]["data"].df = self.ts_ids[self.battv_ts_id]["data"].df.with_columns(pl.Series([10., 10., 10., 10., 10.]).alias("BATTV"))
        result = battery_voltage_check(self.ts_ids, self.value_ts_id, "value_QC_FLAG", self.flag_name, 10., self.battv_ts_id)
        self.assertEqual(result[self.value_ts_id]["data"].df['value_QC_FLAG'].to_list(), [0, 0, 0, 0, 0])

    def test_no_battv_data(self):
        """ Test terror raised when 'BATTV' data is missing.
        """
        self.ts_ids.pop(self.battv_ts_id)
        with self.assertRaises(ValueError):
            battery_voltage_check(self.ts_ids, self.value_ts_id, "value_QC_FLAG", self.flag_name, 10., self.battv_ts_id)


class TestRangeCheck(unittest.TestCase):
    def setUp(self):
        self.flag_name = "range"

        data = pl.DataFrame({
            'time': [
                datetime(2023, 8, 10),
                datetime(2023, 8, 11),
                datetime(2023, 8, 12),
                datetime(2023, 8, 13),
                datetime(2023, 8, 14),
                datetime(2023, 8, 15),
            ],
            'value1': list(range(6)),
        })

        self.ts = TimeSeries(data, "time", metadata={"column_name": "value1"})
        self.ts.add_flag_system("qc_flags", {self.flag_name: 1})
        self.ts.init_flag_column("qc_flags", "value1_QC_FLAG")

        self.value_ts_id = "site1_value1"

        self.ts_ids = {
            self.value_ts_id: {
                "data": self.ts
            }
        }

    def test_range_check(self):
        """ Test that the range check returns expected results when some values outside of range
        """
        gt = 3.5
        lt = 0.5
        result = range_check(self.ts_ids, self.value_ts_id, "value1_QC_FLAG", self.flag_name, gt, lt)
        self.assertEqual(result[self.value_ts_id]["data"].df['value1_QC_FLAG'].to_list(), [1, 0, 0, 0, 1, 1])

    def test_range_check_all_within(self):
        """ Test that the range check returns expected results when all values within range
        """
        gt = 10.
        lt = -1.
        result = range_check(self.ts_ids, self.value_ts_id, "value1_QC_FLAG", self.flag_name, gt, lt)
        self.assertEqual(result[self.value_ts_id]["data"].df['value1_QC_FLAG'].to_list(), [0, 0, 0, 0, 0, 0])

    def test_range_check_all_outside(self):
        """ Test that the range check returns expected results when all values within range
        """
        gt = 100.
        lt = 90.
        result = range_check(self.ts_ids, self.value_ts_id, "value1_QC_FLAG", self.flag_name, gt, lt)
        self.assertEqual(result[self.value_ts_id]["data"].df['value1_QC_FLAG'].to_list(), [1, 1, 1, 1, 1, 1])

    def test_range_check_at_boundaries(self):
        """ Test that the range check returns expected results when values at boundaries
        """
        gt = 5.
        lt = 0.
        result = range_check(self.ts_ids, self.value_ts_id, "value1_QC_FLAG", self.flag_name, gt, lt)
        self.assertEqual(result[self.value_ts_id]["data"].df['value1_QC_FLAG'].to_list(), [0, 0, 0, 0, 0, 0])


class TestSoilmetScansCheck(unittest.TestCase):
    def setUp(self):
        self.flag_name = "samples"

        data = pl.DataFrame({
            'time': [
                datetime(2023, 8, 10),
                datetime(2023, 8, 11),
                datetime(2023, 8, 12),
                datetime(2023, 8, 13),
                datetime(2023, 8, 14),
            ],
            "value": [1., 2., 3., 4., 5.],
        })
        scans_data = pl.DataFrame({
            'time': [
                datetime(2023, 8, 10),
                datetime(2023, 8, 11),
                datetime(2023, 8, 12),
                datetime(2023, 8, 13),
                datetime(2023, 8, 14),
            ],
            "SCANS": [20, 61, 100, 200, 59],
        })

        self.ts = TimeSeries(data, "time", metadata={"column_name": "value"})
        self.ts.add_flag_system("qc_flags", {self.flag_name: 1})
        self.ts.init_flag_column("qc_flags", "value_QC_FLAG")

        scans_ts = TimeSeries(scans_data, "time", metadata={"column_name": "SCANS"})

        self.value_ts_id = "site1_value"
        self.scans_ts_id = "site1_scans_raw"

        self.ts_ids = {
            self.value_ts_id: {
                "data": self.ts
            },
            self.scans_ts_id: {
                "data": scans_ts
            }
        }



    def test_scans_below_threshold(self):
        """ Test that correct flags applied to values that match where SCANS is below threshold
        """
        result = soilmet_scans_check(self.ts_ids, self.value_ts_id, "value_QC_FLAG", self.flag_name, 60., self.scans_ts_id)
        self.assertEqual(result[self.value_ts_id]["data"].df['value_QC_FLAG'].to_list(), [1, 0, 0, 0, 1])

    def test_scans_none_below_threshold(self):
        """ Test that no flags applied because SCANS all above threshold
        """
        result = soilmet_scans_check(self.ts_ids, self.value_ts_id, "value_QC_FLAG", self.flag_name, 1., self.scans_ts_id)
        self.assertEqual(result[self.value_ts_id]["data"].df['value_QC_FLAG'].to_list(), [0, 0, 0, 0, 0])

    def test_scans_all_below_threshold(self):
        """ Test that flags applied to all values because SCANS all below threshold
        """
        result = soilmet_scans_check(self.ts_ids, self.value_ts_id, "value_QC_FLAG", self.flag_name, 1000., self.scans_ts_id)
        self.assertEqual(result[self.value_ts_id]["data"].df['value_QC_FLAG'].to_list(), [1, 1, 1, 1, 1])

    def test_scans_all_at_threshold(self):
        """ Test that no flags applied because SCANS exactly at threshold
        """
        self.ts_ids[self.scans_ts_id]["data"].df = self.ts_ids[self.scans_ts_id]["data"].df.with_columns(pl.Series([60., 60., 60., 60., 60.]).alias("SCANS"))

        result = soilmet_scans_check(self.ts_ids, self.value_ts_id, "value_QC_FLAG", self.flag_name, 60., self.scans_ts_id)
        self.assertEqual(result[self.value_ts_id]["data"].df['value_QC_FLAG'].to_list(), [0, 0, 0, 0, 0])

    def test_no_scans_column(self):
        """ Test error raised when 'SCANS' column is missing.
        """
        self.ts_ids.pop(self.scans_ts_id)
        with self.assertRaises(ValueError):
            soilmet_scans_check(self.ts_ids, self.value_ts_id, "value_QC_FLAG", self.flag_name, 60., self.scans_ts_id)


class TestErrorCodesCheck(unittest.TestCase):
    """Test error_codes_qc function."""

    def setUp(self):
        """Set up a sample DataFrame for testing."""
        self.flag_name = "error_code"
        data = pl.DataFrame({
            'time': [
                datetime(2023, 8, 10),
                datetime(2023, 8, 11),
                datetime(2023, 8, 12),
                datetime(2023, 8, 13),
                datetime(2023, 8, 14),
            ],
            "value": [12.0, 8999, 9.8, 10.2, 7999],
        })

        self.ts = TimeSeries(data, "time", metadata={"column_name": "value"})
        self.ts.add_flag_system("qc_flags", {self.flag_name: 1})
        self.ts.init_flag_column("qc_flags", "value_QC_FLAG")

        self.value_ts_id = "site1_value1"

        self.ts_ids = {
            self.value_ts_id: {
                "data": self.ts
            }
        }

    def test_error_code_qc(self):
        """Test flag correctly raised if values equal the set error codes.
        """
        result = error_codes_check(self.ts_ids, self.value_ts_id, "value_QC_FLAG", self.flag_name, [8999, 7999])
        self.assertEqual(result[self.value_ts_id]["data"].df['value_QC_FLAG'].to_list(), [0, 1, 0, 0, 1])

    def test_error_code_no_error_codes(self):
        """Test flag ot set if no values equal the set error codes.
        """
        result = error_codes_check(self.ts_ids, self.value_ts_id, "value_QC_FLAG", self.flag_name, [0, 1])
        self.assertEqual(result[self.value_ts_id]["data"].df['value_QC_FLAG'].to_list(), [0, 0, 0, 0, 0])


class TestSpikeCheck(unittest.TestCase):
    def setUp(self):
        self.flag_name = "spike"

        data = pl.DataFrame({
            'time': [
                datetime(2023, 8, 10),
                datetime(2023, 8, 11),
                datetime(2023, 8, 12),
                datetime(2023, 8, 13),
                datetime(2023, 8, 14),
                datetime(2023, 8, 15),
            ],
            'value1': [1., 2., 3., 4., 5., 6.],
        })

        self.ts = TimeSeries(data, "time", metadata={"column_name": "value1"})
        self.ts.add_flag_system("qc_flags", {self.flag_name: 1})
        self.ts.init_flag_column("qc_flags", "value1_QC_FLAG")

        self.value_ts_id = "site1_value1"

        self.ts_ids = {
            self.value_ts_id: {
                "data": self.ts
            }
        }

    def test_basic_spike(self):
        """ Test that the spike check returns expected results for a simple spike in the data
        """
        self.ts_ids[self.value_ts_id]["data"].df = self.ts_ids[self.value_ts_id]["data"].df.with_columns(
            pl.Series([1., 2., 3., 40., 5., 6.])
            .alias("value1")
        )

        result = spike_check(self.ts_ids, self.value_ts_id, "value1_QC_FLAG", self.flag_name, 10.)
        self.assertEqual(result[self.value_ts_id]["data"].df['value1_QC_FLAG'].to_list(), [0, 0, 0, 1, 0, 0])

    def test_no_spike(self):
        """ Test that no flags are added for data with no spike
        """
        result = spike_check(self.ts_ids, self.value_ts_id, "value1_QC_FLAG", self.flag_name, 10.)
        self.assertEqual(result[self.value_ts_id]["data"].df['value1_QC_FLAG'].to_list(), [0, 0, 0, 0, 0, 0])

    def test_large_spike(self):
        """ Large spikes can cause the values around the spike to be flagged, if method not working correctly.
        Check this is not the case here.
        """
        self.ts_ids[self.value_ts_id]["data"].df = self.ts_ids[self.value_ts_id]["data"].df.with_columns(
            pl.Series([1., 9999., 3., 4., 999999999., 6.])
            .alias("value1")
        )

        result = spike_check(self.ts_ids, self.value_ts_id, "value1_QC_FLAG", self.flag_name, 10.)
        self.assertEqual(result[self.value_ts_id]["data"].df['value1_QC_FLAG'].to_list(), [0, 1, 0, 0, 1, 0])
