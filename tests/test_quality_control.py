import unittest
from unittest.mock import patch, MagicMock
import polars as pl
from polars.testing import assert_frame_equal

from dritimeseriesprocessor.quality_control import (
    qc_test_map,
    col_comparison_test,
    battery_voltage_test,
    range_test,
    soilmet_scans_test,
    spike_test,
    run_qc
)
from dritimeseriesprocessor.__metadata__.config_quality_control import get_qc_config


class TestColComparison(unittest.TestCase):
    """
    Unit tests for the col_comparison function.
    """
    def setUp(self):
        """
        Set up the initial data for testing.
        This method is run before each test.
        """
        self.data = pl.DataFrame({
            "BATTV": [12.0, 11.5, 9.8, 10.2, 9.5],
            "TA": [20.0, 21.5, 22.1, 19.8, 18.0],
        })
        self.var_col_name = "TA"
        self.threshold = 10.0
        self.flag_value = 5

    def test_col_comparison_test_greater_than(self):
        """
        Test the col_comparison_test function with '>' operator.
        Verifies that the function correctly flags values greater than the threshold.
        """
        result = col_comparison_test(self.data, self.data["BATTV"], self.threshold, self.flag_value, op=">")
        expected_flags = [5, 5, 0, 5, 0]  # Expected flag results based on the data and threshold
        self.assertEqual(result[self.var_col_name].to_list(), expected_flags)

    def test_col_comparison_test_less_than(self):
        """
        Test the col_comparison_test function with '<' operator.
        Verifies that the function correctly flags values less than the threshold.
        """
        result = col_comparison_test(self.data, self.data["BATTV"], self.threshold, self.flag_value, op="<")
        expected_flags = [0, 0, 5, 0, 5]
        self.assertEqual(result[self.var_col_name].to_list(), expected_flags)

    def test_col_comparison_test_invalid_operator(self):
        """
        Test the col_comparison_test function with an invalid operator.
        Verifies that the function raises a ValueError.
        """
        with self.assertRaises(ValueError):
            col_comparison_test(self.data, self.data["BATTV"], self.threshold, self.flag_value, op="invalid_op")


class TestBatteryVoltage(unittest.TestCase):
    """
    Unit tests for the battery voltage function.
    """
    def setUp(self):
        """
        Set up the initial data for testing. 
        This method is run before each test.
        """
        self.data = pl.DataFrame({
            "BATTV": [12.0, 11.5, 9.8, 10.2, 9.5],
            "TA": [20.0, 21.5, 22.1, 19.8, 18.0],
        })
        self.var_col_name = "TA"
        self.flag_col_name = "TA_QCFLAG"
        self.threshold = 10.0
        self.flag_value = 5

    def test_battery_voltage_test(self):
        """
        Test the battery_voltage_test function.
        Verifies that the function correctly applies QC flags based on the battery voltage.
        """
        result = battery_voltage_test(self.data, self.var_col_name, self.flag_col_name, "TEST_SITE")
        expected_flags = [0, 0, 5, 0, 5]  # Expected flag results based on the battery voltage
        self.assertEqual(result[self.flag_col_name].to_list(), expected_flags)

    def test_battery_voltage_test_no_battv_column(self):
        """
        Test the battery_voltage_test function when 'BATTV' column is missing.
        Verifies that the function returns the DataFrame unchanged.
        """
        data_no_battv = self.data.drop(["BATTV"])

        result = battery_voltage_test(data_no_battv, self.var_col_name, self.flag_col_name, "TEST_SITE")

        # Compare the result with the original DataFrame without 'BATTV'
        self.assertEqual(result.shape, data_no_battv.shape)
        self.assertTrue((result.columns == data_no_battv.columns))
        self.assertTrue((result.equals(data_no_battv)))


class TestRunQC(unittest.TestCase):
    """
    Unit tests for the run_qc function.
    """
    def setUp(self):
        """
        Set up the initial data for testing.
        This method is run before each test.
        """
        self.data = pl.DataFrame({
            "BATTV": [12.0, 11.5, 9.8, 10.2, 9.5],
            "TA": [20.0, 21.5, 22.1, 19.8, 18.0],
        })
        self.var_col_name = "TA"
        self.threshold = 10.0
        self.flag_value = 5

    @patch('dritimeseriesprocessor.quality_control.logger')
    def test_run_qc_no_qc_tests_available(self, mock_logger):
        """
        Test the run_qc function when no QC tests are available for a variable.
        Verifies that the function skips QC tests and logs a warning.
        """
        original_qc_test_map = qc_test_map.copy()
        qc_test_map.clear()  # Clear all available QC tests

        result = run_qc(self.data)

        # Ensure no new columns were added due to lack of available tests
        self.assertNotIn(f"{self.var_col_name}_QCFLAG", result.columns)

        # Restore the original test map
        qc_test_map.update(original_qc_test_map)


class TestScanTest(unittest.TestCase):
    def setUp(self):
        self.data = pl.DataFrame({
            "SCANS": [120.0, 140.0, 20.0, 60.1],
            "COL1": [1.0, 2.0, 3.0, 4.0],
            "COL2": [5.0, 6.0, 7.0, 8.0],
            "COL3": [9.0, 10.0, 11.0, 12.0]
        })
        self.var_col_name = "COL2"
        self.flag_col_name = "COL2_QCFLAG"
        self.threshold = 60.0
        self.flag_value = 5


    def test_soilmet_scans_test(self):
        result = soilmet_scans_test(self.data, self.var_col_name, self.flag_col_name, "TEST_SITE")
        expected_flags = [0, 0, 5, 0]
        self.assertEqual(result[f"{self.var_col_name}_QCFLAG"].to_list(), expected_flags)

    @patch('dritimeseriesprocessor.quality_control.logger')
    def test_soilmet_scans_test_no_scans_column(self, mock_logger):
        """
        Test the soilmet_scans_test function when 'SCANS' column is missing.
        Verifies that the function returns the DataFrame unchanged.
        """
        data_no_scans = self.data.drop(["SCANS"])

        result = soilmet_scans_test(data_no_scans, self.var_col_name, self.flag_col_name, "TEST_SITE")

        # Compare the result with the original DataFrame without 'SCANS'
        self.assertEqual(result.shape, data_no_scans.shape)
        self.assertTrue((result.columns == data_no_scans.columns))
        self.assertTrue((result.equals(data_no_scans)))

        # Check logger call
        mock_logger.warning.assert_called_with('Can not run soilmet scans test. No SCANS column in data.')

class TestRangeTest(unittest.TestCase):

    def setUp(self):
        """
        Set up a sample DataFrame for testing.
        """
        self.var_col_name = "TA"
        self.flag_col_name = "TA_QCFLAG"

        self.df = pl.DataFrame({
            "time": ["2023-01-01", "2023-01-02", "2023-01-03"],
            "SITE_ID": ["SITE1", "SITE1", "SITE2"],
            self.var_col_name: [20, 25, 30],
            self.flag_col_name: [0, 0, 0]
        })

    @patch('dritimeseriesprocessor.quality_control.qc_config.get_qc_config')
    @patch('dritimeseriesprocessor.quality_control.logger')
    def test_range_test_no_threshold(self, mock_logger, mock_get_qc_config):
        """
        Test range_test function when no threshold is provided for the column.

        Expected behavior:
        - Function should return the original DataFrame
        - A warning should be logged
        """
        mock_get_qc_config.return_value = {}
        result = range_test(self.df, self.var_col_name, self.flag_col_name, "TEST_SITE")
        assert_frame_equal(result, self.df)
        mock_logger.warning.assert_called_once()

    @patch('dritimeseriesprocessor.quality_control.qc_config.get_qc_config')
    @patch('dritimeseriesprocessor.quality_control.logger')
    def test_range_test_no_default(self, mock_logger, mock_get_qc_config):
        """
        Test range_test function when no default values are set for the column.

        Expected behavior:
        - Function should raise a ValueError
        - An error should be logged
        """
        mock_get_qc_config.return_value = {self.var_col_name: MagicMock(defaults=[])}
        with self.assertRaises(ValueError):
            range_test(self.df, self.var_col_name, self.flag_col_name, "TEST_SITE")
        mock_logger.error.assert_called_once()

    @patch('dritimeseriesprocessor.quality_control.qc_config.get_qc_config')
    @patch('dritimeseriesprocessor.quality_control.add_qcflag_column')
    def test_range_test_default_values(self, mock_add_qcflag, mock_get_qc_config):
        """
        Test range_test function using default values for all sites.

        Expected behavior:
        - QC column should be added to the DataFrame
        - All values should be within range (QC flag = 0)
        """
        mock_get_qc_config.return_value = {
            self.var_col_name: MagicMock(
                defaults=[MagicMock(resolutions=None, min_value=0, max_value=40)],
                sites=[]
            )
        }
        mock_add_qcflag.side_effect = lambda df, flags, column: df.with_columns(pl.lit(0).alias(self.flag_col_name))

        result = range_test(self.df, self.var_col_name, self.flag_col_name, "TEST_SITE")
        self.assertIn(self.flag_col_name, result.columns)
        self.assertEqual(result[self.flag_col_name].to_list(), [0, 0, 0])

    @patch('dritimeseriesprocessor.quality_control.qc_config.get_qc_config')
    @patch('dritimeseriesprocessor.quality_control.add_qcflag_column')
    def test_range_test_site_specific(self, mock_add_qcflag, mock_get_qc_config):
        """
        Test range_test function using site-specific values.

        Expected behavior:
        - QC column should be added to the DataFrame
        - All values should be within range (SITE1 uses site-specific, SITE2 uses default)
        """
        mock_get_qc_config.return_value = {
            self.var_col_name: MagicMock(
                defaults=[MagicMock(resolutions=None, min_value=0, max_value=40)],
                sites=[MagicMock(site_id="SITE1", resolutions=None, min_value=15, max_value=30)]
            )
        }
        mock_add_qcflag.side_effect = lambda df, flags, column: df.with_columns(
            pl.when(flags[column] == 64).then(64).otherwise(0).alias(f"{column}_QCFLAG")
        )

        result = range_test(self.df, self.var_col_name, self.flag_col_name, "TEST_SITE")
        self.assertIn("TA_QCFLAG", result.columns)
        self.assertEqual(result["TA_QCFLAG"].to_list(), [0, 0, 0])

    @patch('dritimeseriesprocessor.quality_control.qc_config.get_qc_config')
    @patch('dritimeseriesprocessor.quality_control.add_qcflag_column')
    def test_range_test_out_of_range(self, mock_add_qcflag, mock_get_qc_config):
        """
        Test range_test function for out-of-range values.

        Expected behavior:
        - QC column should be added to the DataFrame
        - Out-of-range values should be flagged (20 and 30 are out of range)
        """
        mock_get_qc_config.return_value = {
            self.var_col_name: MagicMock(
                defaults=[MagicMock(resolutions=None, min_value=22, max_value=28)],
                sites=[]
            )
        }
        mock_add_qcflag.side_effect = lambda df, flags, column: df.with_columns(
            pl.when(flags[column] == 64).then(64).otherwise(0).alias(f"{column}_QCFLAG")
        )

        result = range_test(self.df, self.var_col_name, self.flag_col_name, "TEST_SITE")
        self.assertIn("TA_QCFLAG", result.columns)
        self.assertEqual(result["TA_QCFLAG"].to_list(), [64, 0, 64])


class TestSpikeTest(unittest.TestCase):
    def setUp(self):
        """Set up the basic DataFrame and configuration mocks."""
        self.site_id = "BUNNY"
        self.var_col_name = "TA"
        self.flag_col_name = "TA_QCFLAG"

        # Example DataFrame setup
        self.df = pl.DataFrame({
            "time": [
                "2023-08-20 00:00",
                "2023-08-20 00:30",
                "2023-08-20 01:00",
                "2023-08-20 01:30",
                "2023-08-20 02:00"],
            "SITE_ID": [self.site_id] * 5,
        })

        # Mock spike configuration
        self.mock_spike_config = {
            self.var_col_name: {
                "defaults": [
                    {
                        "resolutions": ["PT30M"],
                        "threshold": 10.0,
                    },
                ],
            },
        }

    @patch('dritimeseriesprocessor.quality_control.qc_config.get_qc_config')
    @patch('dritimeseriesprocessor.quality_control.get_spike_threshold')
    def test_basic_spike(self, mock_get_spike_threshold, mock_get_qc_config):
        """Test the function with a simple spike in data."""
        mock_get_qc_config.return_value = self.mock_spike_config
        mock_get_spike_threshold.return_value = 20
        df = self.df.with_columns(
            pl.Series([10.1, 9.7, 50.1, 9.5, 8.9]).alias(self.var_col_name),
            pl.Series([0, 0, 0, 0, 0]).alias(self.flag_col_name)
        )

        result = spike_test(df, self.var_col_name, self.flag_col_name, self.site_id)

        # Expected DataFrame after spike test
        expected_df = pl.DataFrame({
            "time": [
                "2023-08-20 00:00",
                "2023-08-20 00:30",
                "2023-08-20 01:00",
                "2023-08-20 01:30",
                "2023-08-20 02:00"
            ],
            "SITE_ID": [self.site_id] * 5,
            self.var_col_name: [10.1, 9.7, 50.1, 9.5, 8.9],
            self.flag_col_name: [0, 0, 512, 0, 0],
        })

        assert_frame_equal(result, expected_df)


    @patch('dritimeseriesprocessor.quality_control.qc_config.get_qc_config')
    @patch('dritimeseriesprocessor.quality_control.get_spike_threshold')
    def test_no_spike(self, mock_get_spike_threshold, mock_get_qc_config):
        """Test the function with data with no spike."""
        mock_get_qc_config.return_value = self.mock_spike_config
        mock_get_spike_threshold.return_value = 20
        df = self.df.with_columns(
            pl.Series([10.1, 9.7, 9.6, 9.5, 8.9]).alias(self.var_col_name),
            pl.Series([0, 0, 0, 0, 0]).alias(self.flag_col_name)
        )

        result = spike_test(df, self.var_col_name, self.flag_col_name, self.site_id)

        # Expected DataFrame after spike test
        expected_df = pl.DataFrame({
            "time": [
                "2023-08-20 00:00",
                "2023-08-20 00:30",
                "2023-08-20 01:00",
                "2023-08-20 01:30",
                "2023-08-20 02:00"
            ],
            "SITE_ID": [self.site_id] * 5,
            self.var_col_name: [10.1, 9.7, 9.6, 9.5, 8.9],
            self.flag_col_name: [0, 0, 0, 0, 0],
        })

        assert_frame_equal(result, expected_df)

    @patch('dritimeseriesprocessor.quality_control.qc_config.get_qc_config')
    @patch('dritimeseriesprocessor.quality_control.get_spike_threshold')
    def test_large_spike(self, mock_get_spike_threshold, mock_get_qc_config):
        """Large spikes can cause the values around the spike to be flagged, if method
        not workign correctly. Check this is not the case here"""
        mock_get_qc_config.return_value = self.mock_spike_config
        mock_get_spike_threshold.return_value = 20
        df = self.df.with_columns(
            pl.Series([10.1, 9.7, 9996, 9.5, 8.9]).alias(self.var_col_name),
            pl.Series([0, 0, 0, 0, 0]).alias(self.flag_col_name)
        )

        result = spike_test(df, self.var_col_name, self.flag_col_name, self.site_id)

        # Expected DataFrame after spike test
        expected_df = pl.DataFrame({
            "time": [
                "2023-08-20 00:00",
                "2023-08-20 00:30",
                "2023-08-20 01:00",
                "2023-08-20 01:30",
                "2023-08-20 02:00"
            ],
            "SITE_ID": [self.site_id] * 5,
            self.var_col_name: [10.1, 9.7, 9996, 9.5, 8.9],
            self.flag_col_name: [0, 0, 512, 0, 0],
        })

        assert_frame_equal(result, expected_df)

    @patch('dritimeseriesprocessor.quality_control.qc_config.get_qc_config')
    @patch('dritimeseriesprocessor.quality_control.get_spike_threshold')
    @patch('dritimeseriesprocessor.quality_control.logger')
    def test_missing_spike_config(self, mock_logger, mock_get_spike_threshold, mock_get_qc_config):
        """Test when spike configuration is missing."""
        mock_get_qc_config.return_value = {}

        result = spike_test(self.df, self.var_col_name, self.flag_col_name, self.site_id)

        # Should log a warning and return the original DataFrame
        mock_logger.warning.assert_called_once_with(f"Can not run spike test. No {self.var_col_name} data provided")
        assert_frame_equal(result, self.df)

    @patch('dritimeseriesprocessor.quality_control.qc_config.get_qc_config')
    @patch('dritimeseriesprocessor.quality_control.get_spike_threshold')
    @patch('dritimeseriesprocessor.quality_control.logger')
    def test_missing_threshold(self, mock_logger, mock_get_spike_threshold, mock_get_qc_config):
        """Test when spike threshold is missing."""
        mock_get_qc_config.return_value = self.mock_spike_config
        mock_get_spike_threshold.return_value = None

        with self.assertRaises(ValueError) as context:
            spike_test(self.df, self.var_col_name, self.flag_col_name, self.site_id)
        self.assertEqual(str(context.exception), f"No default threshold set for {self.var_col_name} spike test")
        mock_logger.error.assert_called_once_with(f"No default threshold set for {self.var_col_name} spike test")


if __name__ == "__main__":
    unittest.main()
