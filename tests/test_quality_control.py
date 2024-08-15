import unittest
from unittest.mock import patch, MagicMock
import polars as pl
from dritimeseriesprocessor.quality_control import (
    qc_test_map,
    col_comparison_test,
    battery_voltage_test,
    range_test,
    soilmet_scans_test,
    run_qc
)

from polars.testing import assert_frame_equal


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
        self.test_column = "TA"
        self.threshold = 10.0
        self.flag_value = 5

    def test_col_comparison_test_greater_than(self):
        """
        Test the col_comparison_test function with '>' operator.
        Verifies that the function correctly flags values greater than the threshold.
        """
        result = col_comparison_test(self.data, self.data["BATTV"], self.threshold, self.flag_value, op=">")
        expected_flags = [5, 5, 0, 5, 0]  # Expected flag results based on the data and threshold
        self.assertEqual(result[self.test_column].to_list(), expected_flags)

    def test_col_comparison_test_less_than(self):
        """
        Test the col_comparison_test function with '<' operator.
        Verifies that the function correctly flags values less than the threshold.
        """
        result = col_comparison_test(self.data, self.data["BATTV"], self.threshold, self.flag_value, op="<")
        expected_flags = [0, 0, 5, 0, 5]
        self.assertEqual(result[self.test_column].to_list(), expected_flags)

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
        self.test_column = "TA"
        self.threshold = 10.0
        self.flag_value = 5

    def test_battery_voltage_test(self):
        """
        Test the battery_voltage_test function.
        Verifies that the function correctly applies QC flags based on the battery voltage.
        """
        result = battery_voltage_test(self.data, self.test_column)
        expected_flags = [0, 0, 5, 0, 5]  # Expected flag results based on the battery voltage
        self.assertEqual(result[f"{self.test_column}_QCFLAG"].to_list(), expected_flags)

    def test_battery_voltage_test_no_battv_column(self):
        """
        Test the battery_voltage_test function when 'BATTV' column is missing.
        Verifies that the function returns the DataFrame unchanged.
        """
        data_no_battv = self.data.drop(["BATTV"])

        result = battery_voltage_test(data_no_battv, self.test_column)

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
        self.test_column = "TA"
        self.threshold = 10.0
        self.flag_value = 5

    def test_run_qc_no_qc_tests_available(self):
        """
        Test the run_qc function when no QC tests are available for a variable.
        Verifies that the function skips QC tests and logs a warning.
        """
        original_qc_test_map = qc_test_map.copy()
        qc_test_map.clear()  # Clear all available QC tests

        result = run_qc(self.data)

        # Ensure no new columns were added due to lack of available tests
        self.assertNotIn(f"{self.test_column}_QCFLAG", result.columns)

        # Restore the original test map
        qc_test_map.update(original_qc_test_map)


class TestScan(unittest.TestCase):
    def setUp(self):
        self.data = pl.DataFrame({
            "SCANS": [120.0, 140.0, 20.0, 60.1],
            "COL1": [1.0, 2.0, 3.0, 4.0],
            "COL2": [5.0, 6.0, 7.0, 8.0],
            "COL3": [9.0, 10.0, 11.0, 12.0]
        })
        self.test_column = "COL2"
        self.threshold = 60.0
        self.flag_value = 5

    def test_soilmet_scans_test(self):
        result = soilmet_scans_test(self.data, self.test_column)
        expected_flags = [0, 0, 5, 0]
        self.assertEqual(result[f"{self.test_column}_QCFLAG"].to_list(), expected_flags)


class TestRangeTest(unittest.TestCase):

    def setUp(self):
        """
        Set up a sample DataFrame for testing.
        """
        self.df = pl.DataFrame({
            "time": ["2023-01-01", "2023-01-02", "2023-01-03"],
            "SITE_ID": ["SITE1", "SITE1", "SITE2"],
            "TA": [20, 25, 30]
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
        result = range_test(self.df, "TA")
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
        mock_get_qc_config.return_value = {"TA": MagicMock(defaults=[])}
        with self.assertRaises(ValueError):
            range_test(self.df, "TA")
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
            "TA": MagicMock(
                defaults=[MagicMock(resolutions=None, min_value=0, max_value=40)],
                sites=[]
            )
        }
        mock_add_qcflag.side_effect = lambda df, flags, column: df.with_columns(pl.lit(0).alias(f"{column}_QCFLAG"))

        result = range_test(self.df, "TA")
        self.assertIn("TA_QCFLAG", result.columns)
        self.assertEqual(result["TA_QCFLAG"].to_list(), [0, 0, 0])

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
            "TA": MagicMock(
                defaults=[MagicMock(resolutions=None, min_value=0, max_value=40)],
                sites=[MagicMock(site_id="SITE1", resolutions=None, min_value=15, max_value=30)]
            )
        }
        mock_add_qcflag.side_effect = lambda df, flags, column: df.with_columns(
            pl.when(flags[column] == 64).then(64).otherwise(0).alias(f"{column}_QCFLAG")
        )

        result = range_test(self.df, "TA")
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
            "TA": MagicMock(
                defaults=[MagicMock(resolutions=None, min_value=22, max_value=28)],
                sites=[]
            )
        }
        mock_add_qcflag.side_effect = lambda df, flags, column: df.with_columns(
            pl.when(flags[column] == 64).then(64).otherwise(0).alias(f"{column}_QCFLAG")
        )

        result = range_test(self.df, "TA")
        self.assertIn("TA_QCFLAG", result.columns)
        self.assertEqual(result["TA_QCFLAG"].to_list(), [64, 0, 64])


if __name__ == "__main__":
    unittest.main()
