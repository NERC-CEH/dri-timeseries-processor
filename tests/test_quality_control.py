import unittest
import polars as pl
from dritimeseriesprocessor.quality_control import qc_test_map, col_comparison_test, battery_voltage_test, run_qc, get_qc_flag, QCTestIDValidator
from dritimeseriesprocessor.__metadata__.config_quality_control import get_qc_config, qc_tests, _qc_test_ids
from parameterized import parameterized
from unittest.mock import patch

class TestQCModule(unittest.TestCase):
    """
    Unit tests for the QC module functions.
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
        self.qc_config = get_qc_config("all")

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

    def test_battery_voltage_test(self):
        """
        Test the battery_voltage_test function.
        Verifies that the function correctly applies QC flags based on the battery voltage.
        """
        battv_flag = _qc_test_ids["BATTV"]
        result = battery_voltage_test(self.data, self.test_column)
        expected_flags = [0, 0, battv_flag, 0, battv_flag]  # Expected flag results based on the battery voltage
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

class TestQCFlagging(unittest.TestCase):
    """Suite for testing the creation of QC flags."""

    @classmethod
    def setUpClass(cls):
        """Set up the test environment by mocking the global variables used in get_qc_config.
        This method is called before each test method.
        """
        # Mock the global variables used in the function
        mock_qc_tests = [
            {
                "test_name": "RANGE",
                "test_id": 1 << 0
            },
            {
                "test_name": "MIN",
                "test_id": 1 << 1
            },
            {
                "test_name": "MAX",
                "test_id": 1 << 2
            },
        ]

        cls.patcher = patch("dritimeseriesprocessor.__metadata__.config_quality_control.qc_tests",mock_qc_tests)
        cls.patcher.start()
    
    @classmethod
    def tearDownClass(cls):
        cls.patcher.stop()
        
    @parameterized.expand([
        ["RANGE", 1],
        [["MIN"], 2],
        ["MAX", 4],
        [["RANGE", "MIN"], 3],
        [["RANGE", "MAX"], 5],
        [["MAX", "MIN"], 6],
        [["RANGE", "MIN", "MAX"], 7],
    ])
    def test_correct_flag_returned(self, test_names, expected):
        """Asserts that the right QC flag is returned for any combination of tests"""

        flag = get_qc_flag(test_names)

        self.assertEqual(flag, expected)

class TestQCTestValidity(unittest.TestCase):
    """Suite to check validity of QC tests in codebase"""

    def setUp(self):
        self.good_tests = [
            {
                "test_name": "RANGE",
                "test_id": 1 << 0
            },
            {
                "test_name": "MIN",
                "test_id": 1 << 1
            },
            {
                "test_name": "MAX",
                "test_id": 1 << 2
            },
        ]

    def test_unique_ids(self):
        """Ensures that all tests have unique IDs"""

        self.assertTrue(
            QCTestIDValidator._ids_are_unique(self.good_tests)
        )

        non_unique_ids = [
            {
                "test_name": "RANGE",
                "test_id": 1 << 0
            },
            {
                "test_name": "MIN",
                "test_id": 1 << 0
            },
            {
                "test_name": "MAX",
                "test_id": 1 << 2
            },
        ]

        self.assertFalse(QCTestIDValidator._ids_are_unique(non_unique_ids))
    
    def test_bitwise_ids(self):
        """Ensures that all test_ids are bitwise (2**n)"""

        self.assertTrue(
            QCTestIDValidator._ids_are_bitwise(self.good_tests)
        )

        bad_tests = [
            {
                "test_name": "RANGE",
                "test_id": 1 << 0
            },
            {
                "test_name": "MIN",
                "test_id": 7
            },
            {
                "test_name": "MAX",
                "test_id": 1.6
            },
        ]

        self.assertFalse(QCTestIDValidator._ids_are_bitwise(bad_tests))
    
    def test_sequential_ids(self):
        """Ensures that all tests have sequential IDs"""

        self.assertTrue(
            QCTestIDValidator._ids_are_sequential(self.good_tests)
        )

        bad_tests = [
            {
                "test_name": "RANGE",
                "test_id": 1 << 1
            },
            {
                "test_name": "MIN",
                "test_id": 1 << 2
            },
            {
                "test_name": "MAX",
                "test_id": 1 << 0
            },
        ]

        self.assertFalse(QCTestIDValidator._ids_are_sequential(bad_tests))

    @patch("dritimeseriesprocessor.quality_control.QCTestIDValidator._ids_are_sequential")
    @patch("dritimeseriesprocessor.quality_control.QCTestIDValidator._ids_are_bitwise")
    @patch("dritimeseriesprocessor.quality_control.QCTestIDValidator._ids_are_unique")
    def test_validation_methods_called(self, mock_ids_are_unique, mock_ids_are_bitwise, mock_ids_are_sequential):
        """Tests that all validation methods are called when main function invoked"""

        assert QCTestIDValidator.validate(self.good_tests)
        assert mock_ids_are_unique.called
        assert mock_ids_are_bitwise.called
        assert mock_ids_are_sequential.called

if __name__ == "__main__":
    unittest.main()
