import unittest
from datetime import datetime
from unittest.mock import patch, Mock

import polars as pl
from time_series import TimeSeries, Period
from polars.testing import assert_frame_equal

from dritimeseriesprocessor.quality_control.checks import (battery_voltage_check, error_codes_check, range_check,
                                                           soilmet_scans_check, spike_check)


class TestBatteryVoltageCheck(unittest.TestCase):
    def setUp(self):
        self.battv_threshold_config = Mock(
            threshold=10.
        )

        data = pl.DataFrame({
            'time': [
                datetime(2023, 8, 10),
                datetime(2023, 8, 11),
                datetime(2023, 8, 12),
                datetime(2023, 8, 13),
                datetime(2023, 8, 14),
            ],
            "BATTV": [12., 11., 9., 13., 8.],
            "value": [1., 2., 3., 4., 5.],
        })

        resolution = Period.of_days(1)
        periodicity = Period.of_days(1)
        self.ts = TimeSeries(
            data,
            "time",
            resolution,
            periodicity
        )

        self.ts.add_flag_system("qc_flags", {
            "BATTV": 1
        })
        self.ts.init_flag_column("qc_flags", "value_QC_FLAG")

    @patch('dritimeseriesprocessor.quality_control.checks.get_qc_config')
    def test_battery_voltage_below_threshold(self, mock_get_qc_config):
        """ Test that correct flags applied to values that match where BATTV is below threshold
        """
        mock_get_qc_config.return_value = self.battv_threshold_config

        result = battery_voltage_check(self.ts, "value", "value_QC_FLAG")
        # Check values below threshold are flagged
        self.assertEqual(result.df['value_QC_FLAG'].to_list(), [0, 0, 1, 0, 1])

    @patch('dritimeseriesprocessor.quality_control.checks.get_qc_config')
    def test_battery_voltage_none_below_threshold(self, mock_get_qc_config):
        """ Test that no flags applied because battery voltage all above threshold
        """
        mock_get_qc_config.return_value = Mock(threshold=0.5)

        result = battery_voltage_check(self.ts, "value", "value_QC_FLAG")
        # Check values below threshold are flagged
        self.assertEqual(result.df['value_QC_FLAG'].to_list(), [0, 0, 0, 0, 0])

    @patch('dritimeseriesprocessor.quality_control.checks.get_qc_config')
    def test_battery_voltage_all_below_threshold(self, mock_get_qc_config):
        """ Test that flags applied to all values because battery voltage all below threshold
        """
        mock_get_qc_config.return_value = Mock(threshold=100.)

        result = battery_voltage_check(self.ts, "value", "value_QC_FLAG")
        # Check values below threshold are flagged
        self.assertEqual(result.df['value_QC_FLAG'].to_list(), [1, 1, 1, 1, 1])

    @patch('dritimeseriesprocessor.quality_control.checks.get_qc_config')
    def test_battery_voltage_all_at_threshold(self, mock_get_qc_config):
        """ Test that no flags applied because battery voltage exactly at threshold
        """
        mock_get_qc_config.return_value = self.battv_threshold_config
        self.ts.df = self.ts.df.with_columns(
            pl.Series([10., 10., 10., 10., 10.])
            .alias("BATTV")
        )

        result = battery_voltage_check(self.ts, "value", "value_QC_FLAG")
        # Check values below threshold are flagged
        self.assertEqual(result.df['value_QC_FLAG'].to_list(), [0, 0, 0, 0, 0])

    @patch('dritimeseriesprocessor.quality_control.checks.get_qc_config')
    def test_no_battv_column(self, mock_get_qc_config):
        """ Test terror raised when 'BATTV' column is missing.
        """
        mock_get_qc_config.return_value = self.battv_threshold_config
        self.ts.df = self.ts.df.drop(["BATTV"])

        with self.assertRaises(UserWarning):
            battery_voltage_check(self.ts, "value", "value_QC_FLAG")


class TestRangeCheck(unittest.TestCase):
    def setUp(self):
        data = pl.DataFrame({
            'time': [
                datetime(2023, 8, 10),
                datetime(2023, 8, 11),
                datetime(2023, 8, 12),
                datetime(2023, 8, 13),
                datetime(2023, 8, 14),
                datetime(2023, 8, 15),
            ],
            'SITE_ID': ['site1'] * 6,
            'value1': list(range(6)),
            'value2': list(range(6, 12)),
        })

        resolution = Period.of_days(1)
        periodicity = Period.of_days(1)
        self.ts = TimeSeries(
            data,
            "time",
            resolution,
            periodicity
        )

        self.ts.add_flag_system("qc_flags", {
            "RANGE": 1
        })
        self.ts.init_flag_column("qc_flags", "value1_QC_FLAG")
        self.ts.init_flag_column("qc_flags", "value2_QC_FLAG")

        self.range_thresholds = {
            "value1": Mock(
                defaults=[
                    Mock(
                        min_value=4,
                        max_value=7,
                        resolutions=["P1D"]
                    )
                ],
                sites=[
                    Mock(
                        site_id="site1",
                        min_value=1,
                        max_value=3,
                        resolutions=["P1D"]
                    )
                ]
            ),

            "value2": Mock(
                defaults=[
                    Mock(
                        min_value=10,
                        max_value=13,
                        resolutions=None
                    )
                ],
                sites=[]
            )
        }

    @patch('dritimeseriesprocessor.quality_control.utils.get_qc_config')
    def test_range_check_site_specific(self, mock_get_qc_config):
        """ Test that the range check returns expected results when 1 site has site specific range thresholds,
        and one site has to use default range thresholds.
        """
        mock_get_qc_config.return_value = self.range_thresholds

        result = range_check(self.ts, "value1", "value1_QC_FLAG")
        # Check values out of range are flagged
        self.assertEqual(result.df['value1_QC_FLAG'].to_list(), [1, 0, 0, 0, 1, 1])

    @patch('dritimeseriesprocessor.quality_control.utils.get_qc_config')
    def test_range_check_default_only(self, mock_get_qc_config):
        """ Test that the range check returns expected results when all sites use defaults
        """
        mock_get_qc_config.return_value = self.range_thresholds

        result = range_check(self.ts, "value2", "value2_QC_FLAG")
        # Check values out of range are flagged
        self.assertEqual(result.df['value2_QC_FLAG'].to_list(), [1, 1, 1, 1, 0, 0])

    @patch('dritimeseriesprocessor.quality_control.utils.get_qc_config')
    def test_range_qc_no_threshold(self, mock_get_qc_config):
        """ Test error raised when no threshold is provided.
        """
        mock_get_qc_config.return_value = self.range_thresholds
        with self.assertRaises(UserWarning):
            range_check(self.ts, "value3", "value3_QC_FLAG")

    @patch('dritimeseriesprocessor.quality_control.utils.get_qc_config')
    def test_range_qc_no_default(self, mock_get_qc_config):
        """ Test error raised when no default is provided for values with no site specific thresholds.
        """
        range_thresholds = self.range_thresholds.copy()
        range_thresholds["value2"].defaults = []

        mock_get_qc_config.return_value = range_thresholds

        with self.assertRaises(ValueError):
            range_check(self.ts, "value2", "value2_QC_FLAG")


class TestSoilmetScansCheck(unittest.TestCase):
    def setUp(self):
        self.soilmet_scans_threshold_config = Mock(
            threshold=60.
        )

        data = pl.DataFrame({
            'time': [
                datetime(2023, 8, 10),
                datetime(2023, 8, 11),
                datetime(2023, 8, 12),
                datetime(2023, 8, 13),
                datetime(2023, 8, 14),
            ],
            "SCANS": [20, 61, 100, 200, 59],
            "value": [1., 2., 3., 4., 5.],
        })

        resolution = Period.of_days(1)
        periodicity = Period.of_days(1)
        self.ts = TimeSeries(
            data,
            "time",
            resolution,
            periodicity
        )

        self.ts.add_flag_system("qc_flags", {
            "SCANS": 1
        })
        self.ts.init_flag_column("qc_flags", "value_QC_FLAG")

    @patch('dritimeseriesprocessor.quality_control.checks.get_qc_config')
    def test_scans_below_threshold(self, mock_get_qc_config):
        """ Test that correct flags applied to values that match where SCANS is below threshold
        """
        mock_get_qc_config.return_value = self.soilmet_scans_threshold_config

        result = soilmet_scans_check(self.ts, "value", "value_QC_FLAG")
        # Check values below threshold are flagged
        self.assertEqual(result.df['value_QC_FLAG'].to_list(), [1, 0, 0, 0, 1])

    @patch('dritimeseriesprocessor.quality_control.checks.get_qc_config')
    def test_scans_none_below_threshold(self, mock_get_qc_config):
        """ Test that no flags applied because SCANS all above threshold
        """
        mock_get_qc_config.return_value = Mock(threshold=1)

        result = soilmet_scans_check(self.ts, "value", "value_QC_FLAG")
        # Check values below threshold are flagged
        self.assertEqual(result.df['value_QC_FLAG'].to_list(), [0, 0, 0, 0, 0])

    @patch('dritimeseriesprocessor.quality_control.checks.get_qc_config')
    def test_scans_all_below_threshold(self, mock_get_qc_config):
        """ Test that flags applied to all values because SCANS all below threshold
        """
        mock_get_qc_config.return_value = Mock(threshold=1000.)

        result = soilmet_scans_check(self.ts, "value", "value_QC_FLAG")
        # Check values below threshold are flagged
        self.assertEqual(result.df['value_QC_FLAG'].to_list(), [1, 1, 1, 1, 1])

    @patch('dritimeseriesprocessor.quality_control.checks.get_qc_config')
    def test_scans_all_at_threshold(self, mock_get_qc_config):
        """ Test that no flags applied because SCANS exactly at threshold
        """
        mock_get_qc_config.return_value = self.soilmet_scans_threshold_config
        self.ts.df = self.ts.df.with_columns(
            pl.Series([60., 60., 60., 60., 60.])
            .alias("SCANS")
        )

        result = soilmet_scans_check(self.ts, "value", "value_QC_FLAG")
        # Check values below threshold are flagged
        self.assertEqual(result.df['value_QC_FLAG'].to_list(), [0, 0, 0, 0, 0])

    @patch('dritimeseriesprocessor.quality_control.checks.get_qc_config')
    def test_no_scans_column(self, mock_get_qc_config):
        """ Test error raised when 'SCANS' column is missing.
        """
        mock_get_qc_config.return_value = self.soilmet_scans_threshold_config

        self.ts.df = self.ts.df.drop(["SCANS"])
        with self.assertRaises(UserWarning):
            soilmet_scans_check(self.ts, "value", "value_QC_FLAG")


class TestErrorCodesCheck(unittest.TestCase):
    """Test error_codes_qc function."""

    def setUp(self):
        """Set up a sample DataFrame for testing."""
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

        resolution = Period.of_days(1)
        periodicity = Period.of_days(1)
        self.ts = TimeSeries(
            data,
            "time",
            resolution,
            periodicity
        )

        self.ts.add_flag_system("qc_flags", {
            "ERROR_CODES": 1
        })
        self.ts.init_flag_column("qc_flags", "value_QC_FLAG")


    def test_error_code_qc(self):
        """Test flag correctly raised if values equal the set error codes.
        """
        result = error_codes_check(self.ts, "value", "value_QC_FLAG")
        self.assertEqual(result.df['value_QC_FLAG'].to_list(), [0, 1, 0, 0, 1])


class TestSpikeCheck(unittest.TestCase):
    def setUp(self):
        data = pl.DataFrame({
            'time': [
                datetime(2023, 8, 10),
                datetime(2023, 8, 11),
                datetime(2023, 8, 12),
                datetime(2023, 8, 13),
                datetime(2023, 8, 14),
                datetime(2023, 8, 15),
            ],
            'SITE_ID': ['site1'] * 6,
            'value1': [1., 2., 3., 4., 5., 6.],
            'value2': [100., 105., 110., 115., 120., 125.],
        })

        resolution = Period.of_days(1)
        periodicity = Period.of_days(1)
        self.ts = TimeSeries(
            data,
            "time",
            resolution,
            periodicity
        )

        self.ts.add_flag_system("qc_flags", {
            "SPIKE": 1
        })
        self.ts.init_flag_column("qc_flags", "value1_QC_FLAG")
        self.ts.init_flag_column("qc_flags", "value2_QC_FLAG")

        self.spike_thresholds = {
            "value1": Mock(
                defaults=[
                    Mock(
                        threshold=10.,
                        resolutions=["P1D"]
                    )
                ],
                sites=[]
            ),
            "value2": Mock(
                defaults=[
                    Mock(
                        threshold=20.,
                        resolutions=["P1D"]
                    )
                ],
                sites=[]
            ),
        }


    @patch('dritimeseriesprocessor.quality_control.utils.get_qc_config')
    def test_basic_spike(self, mock_get_qc_config):
        """ Test that the spike check returns expected results for a simple spike in the data
        """
        mock_get_qc_config.return_value = self.spike_thresholds

        self.ts.df = self.ts.df.with_columns(
            pl.Series([1., 2., 3., 40., 5., 6.])
            .alias("value1")
        )

        result = spike_check(self.ts, "value1", "value1_QC_FLAG")
        # Check spike values are flagged
        self.assertEqual(result.df['value1_QC_FLAG'].to_list(), [0, 0, 0, 1, 0, 0])

    @patch('dritimeseriesprocessor.quality_control.utils.get_qc_config')
    def test_no_spike(self, mock_get_qc_config):
        """ Test that no flags are added for data with no spike
        """
        mock_get_qc_config.return_value = self.spike_thresholds

        result = spike_check(self.ts, "value1", "value1_QC_FLAG")
        # Check spike values are flagged
        self.assertEqual(result.df['value1_QC_FLAG'].to_list(), [0, 0, 0, 0, 0, 0])

    @patch('dritimeseriesprocessor.quality_control.utils.get_qc_config')
    def test_large_spike(self, mock_get_qc_config):
        """ Large spikes can cause the values around the spike to be flagged, if method not working correctly.
        Check this is not the case here.
        """
        mock_get_qc_config.return_value = self.spike_thresholds

        self.ts.df = self.ts.df.with_columns(
            pl.Series([1., 9999., 3., 4., 999999999., 6.])
            .alias("value1")
        )

        result = spike_check(self.ts, "value1", "value1_QC_FLAG")
        # Check spike values are flagged
        self.assertEqual(result.df['value1_QC_FLAG'].to_list(), [0, 1, 0, 0, 1, 0])

    @patch('dritimeseriesprocessor.quality_control.utils.get_qc_config')
    def test_spike_qc_no_threshold(self, mock_get_qc_config):
        """ Test error raised when no threshold is provided.
        """
        mock_get_qc_config.return_value = self.spike_thresholds
        with self.assertRaises(UserWarning):
            spike_check(self.ts, "value3", "value3_QC_FLAG")

    @patch('dritimeseriesprocessor.quality_control.utils.get_qc_config')
    def test_spike_qc_no_default(self, mock_get_qc_config):
        """ Test error raised when no default is provided for values with no site specific thresholds.
        """
        spike_thresholds = self.spike_thresholds.copy()
        spike_thresholds["value1"].defaults = []
        mock_get_qc_config.return_value = spike_thresholds

        with self.assertRaises(ValueError):
            spike_check(self.ts, "value1", "value1_QC_FLAG")
