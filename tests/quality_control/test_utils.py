import unittest
import polars as pl

from dritimeseriesprocessor.quality_control.utils import col_comparison_test


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


if __name__ == "__main__":
    unittest.main()