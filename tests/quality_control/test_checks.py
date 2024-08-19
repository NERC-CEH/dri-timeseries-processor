import unittest
from unittest.mock import patch, Mock

import polars as pl
from polars.testing import assert_frame_equal

from dritimeseriesprocessor.quality_control.checks import (battery_voltage_check, range_check, soilmet_scans_check)


class TestBatteryVoltageCheck(unittest.TestCase):
    def setUp(self):
        self.battv_threshold_config = Mock(
            threshold=10.
        )

        self.data = pl.DataFrame({
            "BATTV": [12., 11., 9., 13., 8.],
            "value": [1., 2., 3., 4., 5.],
        })

        self.flag_value = 1

    @patch('dritimeseriesprocessor.quality_control.checks.get_qc_config')
    def test_battery_voltage_below_threshold(self, mock_get_qc_config):
        """ Test that correct flags applied to values that match where BATTV is below threshold
        """
        mock_get_qc_config.return_value = self.battv_threshold_config

        result = battery_voltage_check(self.data, "value", self.flag_value)
        expected = self.data.with_columns(
            pl.Series([0, 0, self.flag_value, 0, self.flag_value])
            .alias("value_QCFLAG")
        )
        assert_frame_equal(result, expected)

    @patch('dritimeseriesprocessor.quality_control.checks.get_qc_config')
    def test_battery_voltage_none_below_threshold(self, mock_get_qc_config):
        """ Test that no flags applied because battery voltage all above threshold
        """
        mock_get_qc_config.return_value = Mock(threshold=0.5)

        result = battery_voltage_check(self.data, "value", self.flag_value)
        expected = self.data.with_columns(
            pl.Series([0, 0, 0, 0, 0])
            .alias("value_QCFLAG")
        )
        assert_frame_equal(result, expected)

    @patch('dritimeseriesprocessor.quality_control.checks.get_qc_config')
    def test_battery_voltage_all_below_threshold(self, mock_get_qc_config):
        """ Test that flags applied to all values because battery voltage all below threshold
        """
        mock_get_qc_config.return_value = Mock(threshold=100.)

        result = battery_voltage_check(self.data, "value", self.flag_value)
        expected = self.data.with_columns(
            pl.Series([self.flag_value, self.flag_value, self.flag_value, self.flag_value, self.flag_value])
            .alias("value_QCFLAG")
        )
        assert_frame_equal(result, expected)

    @patch('dritimeseriesprocessor.quality_control.checks.get_qc_config')
    def test_battery_voltage_all_at_threshold(self, mock_get_qc_config):
        """ Test that no flags applied because battery voltage exactly at threshold
        """
        mock_get_qc_config.return_value = self.battv_threshold_config
        new_data = self.data.with_columns(
            pl.Series([10., 10., 10., 10., 10.])
            .alias("BATTV")
        )

        result = battery_voltage_check(new_data, "value", self.flag_value)
        expected = new_data.with_columns(
            pl.Series([0, 0, 0, 0, 0])
            .alias("value_QCFLAG")
        )
        assert_frame_equal(result, expected)

    @patch('dritimeseriesprocessor.quality_control.checks.get_qc_config')
    def test_no_battv_column(self, mock_get_qc_config):
        """ Test terror raised when 'BATTV' column is missing.
        """
        mock_get_qc_config.return_value = self.battv_threshold_config
        with self.assertRaises(UserWarning):
            battery_voltage_check(self.data.drop(["BATTV"]), "value", self.flag_value)


class TestRangeCheck(unittest.TestCase):
    def setUp(self):
        self.data = pl.DataFrame({
            'SITE_ID': ['site1'] * 6 + ['site2'] * 6,
            'value1': list(range(6)) * 2,
            'value2': list(range(6, 12)) * 2
        })

        self.range_thresholds = {
            "value1": Mock(
                defaults=[
                    Mock(
                        min_value=4,
                        max_value=7,
                        resolutions=["PT30M"]
                    )
                ],
                sites=[
                    Mock(
                        site_id="site1",
                        min_value=1,
                        max_value=3,
                        resolutions=["PT30M"]
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

        self.flag_value = 1

    @patch('dritimeseriesprocessor.quality_control.utils.get_qc_config')
    def test_range_check_default_and_site_specific(self, mock_get_qc_config):
        """ Test that the range check returns expected results when 1 site has site specific range thresholds,
        and one site has to use default range thresholds.
        """
        mock_get_qc_config.return_value = self.range_thresholds

        result = range_check(self.data, "value1", self.flag_value)

        expected = self.data.with_columns(
            pl.Series([self.flag_value, 0, 0, 0, self.flag_value, self.flag_value,
                              self.flag_value, self.flag_value, self.flag_value, self.flag_value, 0, 0])
            .alias("value1_QCFLAG")
        )

        assert_frame_equal(result, expected)

    @patch('dritimeseriesprocessor.quality_control.utils.get_qc_config')
    def test_range_check_default_only(self, mock_get_qc_config):
        """ Test that the range check returns expected results when all sites use defaults
        """
        mock_get_qc_config.return_value = self.range_thresholds

        result = range_check(self.data, "value2", self.flag_value)

        expected = self.data.with_columns(
            pl.Series([self.flag_value, self.flag_value, self.flag_value, self.flag_value, 0, 0,
                       self.flag_value, self.flag_value, self.flag_value, self.flag_value, 0, 0])
            .alias("value2_QCFLAG")
        )

        assert_frame_equal(result, expected)

    @patch('dritimeseriesprocessor.quality_control.utils.get_qc_config')
    def test_range_qc_no_threshold(self, mock_get_qc_config):
        """ Test error raised when no threshold is provided.
        """
        mock_get_qc_config.return_value = self.range_thresholds
        with self.assertRaises(UserWarning):
            range_check(self.data, "value3", self.flag_value)

    @patch('dritimeseriesprocessor.quality_control.utils.get_qc_config')
    def test_range_qc_no_default(self, mock_get_qc_config):
        """ Test error raised when no default is provided for values with no site specific thresholds.
        """
        range_thresholds = self.range_thresholds.copy()
        range_thresholds["value1"].defaults = []

        mock_get_qc_config.return_value = range_thresholds

        with self.assertRaises(ValueError):
            range_check(self.data, "value1", self.flag_value)


class TestSoilmetScansCheck(unittest.TestCase):
    def setUp(self):
        self.soilmet_scans_threshold_config = Mock(
            threshold=60.
        )

        self.data = pl.DataFrame({
            "SCANS": [20, 61, 100, 200, 59],
            "value": [1., 2., 3., 4., 5.],
        })

        self.flag_value = 1

    @patch('dritimeseriesprocessor.quality_control.checks.get_qc_config')
    def test_scans_below_threshold(self, mock_get_qc_config):
        """ Test that correct flags applied to values that match where SCANS is below threshold
        """
        mock_get_qc_config.return_value = self.soilmet_scans_threshold_config

        result = soilmet_scans_check(self.data, "value", self.flag_value)
        expected = self.data.with_columns(
            pl.Series([self.flag_value, 0, 0, 0, self.flag_value])
            .alias("value_QCFLAG")
        )
        assert_frame_equal(result, expected)

    @patch('dritimeseriesprocessor.quality_control.checks.get_qc_config')
    def test_scans_none_below_threshold(self, mock_get_qc_config):
        """ Test that no flags applied because SCANS all above threshold
        """
        mock_get_qc_config.return_value = Mock(threshold=1)

        result = soilmet_scans_check(self.data, "value", self.flag_value)
        expected = self.data.with_columns(
            pl.Series([0, 0, 0, 0, 0])
            .alias("value_QCFLAG")
        )
        assert_frame_equal(result, expected)

    @patch('dritimeseriesprocessor.quality_control.checks.get_qc_config')
    def test_scans_all_below_threshold(self, mock_get_qc_config):
        """ Test that flags applied to all values because SCANS all below threshold
        """
        mock_get_qc_config.return_value = Mock(threshold=1000.)

        result = soilmet_scans_check(self.data, "value", self.flag_value)
        expected = self.data.with_columns(
            pl.Series([self.flag_value, self.flag_value, self.flag_value, self.flag_value, self.flag_value])
            .alias("value_QCFLAG")
        )
        assert_frame_equal(result, expected)

    @patch('dritimeseriesprocessor.quality_control.checks.get_qc_config')
    def test_scans_all_at_threshold(self, mock_get_qc_config):
        """ Test that no flags applied because SCANS exactly at threshold
        """
        mock_get_qc_config.return_value = self.soilmet_scans_threshold_config
        new_data = self.data.with_columns(
            pl.Series([60., 60., 60., 60., 60.])
            .alias("SCANS")
        )

        result = soilmet_scans_check(new_data, "value", self.flag_value)
        expected = new_data.with_columns(
            pl.Series([0, 0, 0, 0, 0])
            .alias("value_QCFLAG")
        )
        assert_frame_equal(result, expected)

    @patch('dritimeseriesprocessor.quality_control.checks.get_qc_config')
    def test_no_scans_column(self, mock_get_qc_config):
        """ Test error raised when 'SCANS' column is missing.
        """
        mock_get_qc_config.return_value = self.soilmet_scans_threshold_config
        with self.assertRaises(UserWarning):
            battery_voltage_check(self.data.drop(["SCANS"]), "value", self.flag_value)
