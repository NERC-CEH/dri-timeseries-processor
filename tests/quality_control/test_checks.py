import unittest
from unittest.mock import patch, MagicMock
import polars as pl
from polars.testing import assert_frame_equal

from dritimeseriesprocessor.quality_control.checks import (
    battery_voltage_qc,
    range_qc,
    soilmet_scans_qc,
)

from dritimeseriesprocessor.__metadata__.config_quality_control import qc_tests

class TestBatteryVoltageQC(unittest.TestCase):
    """Unit tests for the battery voltage function."""
    def setUp(self):
        """
        Set up the initial data for testing. 
        This method is run before each test.
        """
        self.data = pl.DataFrame({
            "BATTV": [12.0, 11.5, 9.8, 10.2, 9.5],
            "TA": [20.0, 21.5, 22.1, 19.8, 18.0],
        })
        self.test_column = "TA"
        self.threshold = 10.0
        self.flag_value = 5

    def test_battery_voltage_qc(self):
        """
        Test the battery_voltage_qc function.
        Verifies that the function correctly applies QC flags based on the battery voltage.
        """
        battv_flag = qc_tests["BATTV"]["id"]
        result = battery_voltage_qc(self.data, self.test_column)
        expected_flags = [0, 0, battv_flag, 0, battv_flag]
        self.assertEqual(result[f"{self.test_column}_QCFLAG"].to_list(), expected_flags)

    def test_battery_voltage_qc_no_battv_column(self):
        """
        Test the battery_voltage_qc function when 'BATTV' column is missing.
        Verifies that the function returns the DataFrame unchanged.
        """
        data_no_battv = self.data.drop(["BATTV"])

        result = battery_voltage_qc(data_no_battv, self.test_column)

        # Compare the result with the original DataFrame without 'BATTV'
        self.assertEqual(result.shape, data_no_battv.shape)
        self.assertTrue((result.columns == data_no_battv.columns))
        self.assertTrue((result.equals(data_no_battv)))


class TestScanQC(unittest.TestCase):
    """Unit tests for the soilmet_scans function."""
    def setUp(self):
        self.data = pl.DataFrame({
            "SCANS": [120.0, 140.0, 20.0, 60.1],
            "COL1": [1.0, 2.0, 3.0, 4.0],
            "COL2": [5.0, 6.0, 7.0, 8.0],
            "COL3": [9.0, 10.0, 11.0, 12.0]
        })
        self.test_column = "COL2"
        self.threshold = 60.0
        self.flag_value = qc_tests["SCANS"]["id"]

    def test_soilmet_scans_qc(self):
        result = soilmet_scans_qc(self.data, self.test_column)
        expected_flags = [0, 0, self.flag_value, 0]
        self.assertEqual(result[f"{self.test_column}_QCFLAG"].to_list(), expected_flags)

    @patch('dritimeseriesprocessor.quality_control.checks.logger')
    def test_soilmet_scans_qc_no_scans_column(self, mock_logger):
        """
        Test the soilmet_scans_qc function when 'SCANS' column is missing.
        Verifies that the function returns the DataFrame unchanged.
        """
        data_no_scans = self.data.drop(["SCANS"])

        result = soilmet_scans_qc(data_no_scans, self.test_column)

        # Compare the result with the original DataFrame without 'SCANS'
        self.assertEqual(result.shape, data_no_scans.shape)
        self.assertTrue((result.columns == data_no_scans.columns))
        self.assertTrue((result.equals(data_no_scans)))

        # Check logger call
        mock_logger.warning.assert_called_with('Can not run soilmet scans test. No SCANS column in data.')


class TestRangeQC(unittest.TestCase):
    """Unit tests for the range function."""
    def setUp(self):
        """
        Set up a sample DataFrame for testing.
        """
        self.df = pl.DataFrame({
            "time": ["2023-01-01", "2023-01-02", "2023-01-03"],
            "SITE_ID": ["SITE1", "SITE1", "SITE2"],
            "TA": [20, 25, 30]
        })

    @patch('dritimeseriesprocessor.quality_control.quality_control.qc_config.get_qc_config')
    @patch('dritimeseriesprocessor.quality_control.checks.logger')
    def test_range_qc_no_threshold(self, mock_logger, mock_get_qc_config):
        """
        Test range_qc function when no threshold is provided for the column.

        Expected behavior:
        - Function should return the original DataFrame
        - A warning should be logged
        """
        mock_get_qc_config.return_value = {}
        result = range_qc(self.df, "TA")
        assert_frame_equal(result, self.df)
        mock_logger.warning.assert_called_once()

    @patch('dritimeseriesprocessor.quality_control.quality_control.qc_config.get_qc_config')
    @patch('dritimeseriesprocessor.quality_control.checks.logger')
    def test_range_qc_no_default(self, mock_logger, mock_get_qc_config):
        """
        Test range_qc function when no default values are set for the column.

        Expected behavior:
        - Function should raise a ValueError
        - An error should be logged
        """
        mock_get_qc_config.return_value = {"TA": MagicMock(defaults=[])}
        with self.assertRaises(ValueError):
            range_qc(self.df, "TA")
        mock_logger.error.assert_called_once()

    @patch('dritimeseriesprocessor.quality_control.quality_control.qc_config.get_qc_config')
    @patch('dritimeseriesprocessor.quality_control.utils.add_qcflag_column')
    def test_range_qc_default_values(self, mock_add_qcflag, mock_get_qc_config):
        """
        Test range_qc function using default values for all sites.

        Expected behavior:
        - QC column should be added to the DataFrame
        - All values should be within range (QC flag = 0)
        """
        mock_get_qc_config.return_value = {
            "TA": MagicMock(
                defaults=[MagicMock(resolutions=None, min_value=0, max_value=40)],
                sites=[]
            )
        }
        mock_add_qcflag.side_effect = lambda df, flags, column: df.with_columns(pl.lit(0).alias(f"{column}_QCFLAG"))

        result = range_qc(self.df, "TA")
        self.assertIn("TA_QCFLAG", result.columns)
        self.assertEqual(result["TA_QCFLAG"].to_list(), [0, 0, 0])

    @patch('dritimeseriesprocessor.quality_control.quality_control.qc_config.get_qc_config')
    @patch('dritimeseriesprocessor.quality_control.utils.add_qcflag_column')
    def test_range_qc_site_specific(self, mock_add_qcflag, mock_get_qc_config):
        """
        Test range_qc function using site-specific values.

        Expected behavior:
        - QC column should be added to the DataFrame
        - All values should be within range (SITE1 uses site-specific, SITE2 uses default)
        """
        qc_flag = qc_tests["RANGE"]["id"]
        mock_get_qc_config.return_value = {
            "TA": MagicMock(
                defaults=[MagicMock(resolutions=None, min_value=0, max_value=40)],
                sites=[MagicMock(site_id="SITE1", resolutions=None, min_value=15, max_value=30)]
            )
        }
        mock_add_qcflag.side_effect = lambda df, flags, column: df.with_columns(
            pl.when(flags[column] == qc_flag).then(qc_flag).otherwise(0).alias(f"{column}_QCFLAG")
        )

        result = range_qc(self.df, "TA")
        self.assertIn("TA_QCFLAG", result.columns)
        self.assertEqual(result["TA_QCFLAG"].to_list(), [0, 0, 0])

    @patch('dritimeseriesprocessor.quality_control.quality_control.qc_config.get_qc_config')
    @patch('dritimeseriesprocessor.quality_control.utils.add_qcflag_column')
    def test_range_qc_out_of_range(self, mock_add_qcflag, mock_get_qc_config):
        """
        Test range_qc function for out-of-range values.

        Expected behavior:
        - QC column should be added to the DataFrame
        - Out-of-range values should be flagged (20 and 30 are out of range)
        """
        qc_flag = qc_tests["RANGE"]["id"]
        mock_get_qc_config.return_value = {
            "TA": MagicMock(
                defaults=[MagicMock(resolutions=None, min_value=22, max_value=28)],
                sites=[]
            )
        }
        mock_add_qcflag.side_effect = lambda df, flags, column: df.with_columns(
            pl.when(flags[column] == qc_flag).then(qc_flag).otherwise(0).alias(f"{column}_QCFLAG")
        )

        result = range_qc(self.df, "TA")
        self.assertIn("TA_QCFLAG", result.columns)
        self.assertEqual(result["TA_QCFLAG"].to_list(), [qc_flag, 0, qc_flag])
