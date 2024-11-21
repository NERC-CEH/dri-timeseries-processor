import unittest
from unittest.mock import patch, MagicMock

from datetime import datetime
import polars as pl
from parameterized import parameterized
import numpy as np

from time_series import TimeSeries
from dritimeseriesprocessor.flagging import (
    initialise_core_flags,
    add_flag_columns,
    add_unchecked_flag,
    add_missing_flag
)


mock_core_flag_config = {
    "unchecked": MagicMock(id=1),
    "missing": MagicMock(id=2)
}


class TestInitialiseCoreFlags(unittest.TestCase):

    def test_initialise_core_flags(self):
        """Test that initialise_core_flags adds flag columns correctly.
        """
        with patch.dict('dritimeseriesprocessor.__metadata__.config_core_flags.core_flag_config', 
                        mock_core_flag_config, clear=True):
            # Create a sample DataFrame
            df = pl.DataFrame({
                "time": [datetime(2024, 1, 1), datetime(2024, 1, 2), datetime(2024, 1, 3)],
                "data_col1": [1, 2, 3],
                "data_col2": [1, 2, 3]
            })

            # Create a TimeSeries object from the DataFrame
            ts = TimeSeries.from_polars(df, "time")

            # Call the function to add flag columns
            result = initialise_core_flags(ts)

            # Check if the new flag columns were added with the correct mock value
            self.assertIn("data_col1_FLAG", result.df.columns)
            self.assertIn("data_col2_FLAG", result.df.columns)
            self.assertIn("data_col1_FLAG", result.supp_col_names)
            self.assertIn("data_col2_FLAG", result.supp_col_names)
            self.assertNotIn("data_col1_FLAG", result.data_col_names)
            self.assertNotIn("data_col2_FLAG", result.data_col_names)

    def test_initialise_core_flags_no_columns(self):
        """Test that an empty DataFrame does not add any flag columns.
        """
        with patch.dict('dritimeseriesprocessor.__metadata__.config_core_flags.core_flag_config', 
                        mock_core_flag_config, clear=True):
            # Create a DataFrame with only a time column (no data columns)
            df = pl.DataFrame({
                "time": [datetime(2024, 1, 1), datetime(2024, 1, 2), datetime(2024, 1, 3)]
            })
            ts = TimeSeries.from_polars(df, "time")

            # Call the function
            result = initialise_core_flags(ts)

            # Ensure no flag columns are added
            self.assertEqual(result.df.columns, ["time"])


class TestAddFlagColumns(unittest.TestCase):
    """Unit tests for the add_flag_columns function."""
    def setUp(self):
        """Set up a sample DataFrame for testing."""
        self.df = pl.DataFrame({
            "data": [10, 20, 30]
        })

    @parameterized.expand([
        ("One column", ["flag1"]),
        ("multi columns", ["flag1", "flag2", "flag3"]),
        ("No columns", []),
    ])
    def test_add_columns(self, name, col_names):
        """Test columns are successfully added, set to 0's"""
        result = add_flag_columns(self.df, col_names)
        expected_cols = ["data"] + col_names
        self.assertEqual(result.columns, expected_cols)

        for col_name in col_names:
            self.assertEqual(result[col_name].to_list(), [0, 0, 0])


class TestAddUncheckedFlag(unittest.TestCase):
    """Unit tests for the add_unchecked_flag function."""

    def setUp(self):
        """Set up a sample DataFrame for testing."""
        self.df = pl.DataFrame({
            "data1": [1, 2, 3],
            "flag1": [0, 0, 0],
            "data2": [10, 20, 30],
            "flag2": [0, 0, 0],
        })

    def test_add_unchecked_flag(self):
        """Test that add_unchecked_flag correctly updates the flag column.
        """
        with patch.dict('dritimeseriesprocessor.__metadata__.config_core_flags.core_flag_config',
                        mock_core_flag_config, clear=True):
            # Call the function
            result = add_unchecked_flag(self.df, ["flag1", "flag2"])

            # Expected result
            expected_df = pl.DataFrame({
                "data1": [1, 2, 3],
                "flag1": [1, 1, 1],  # All values in the flag column should be updated to 1
                "data2": [10, 20, 30],
                "flag2": [1, 1, 1],  # All values in the flag column should be updated to 1
            })

            # Check if the result matches the expected DataFrame
            self.assertTrue(result.equals(expected_df), "The DataFrames are not equal.")

    def test_nonexistent_flag_column(self):
        """Test behavior when the specified flag column does not exist."""
        with self.assertRaises(pl.exceptions.ColumnNotFoundError):
            add_unchecked_flag(self.df, ["nonexistent_flag"])


class TestAddMissingFlag(unittest.TestCase):
    """Unit tests for the add_missing_flag function."""

    def setUp(self):
        """Set up a sample DataFrame for testing."""
        self.df = pl.DataFrame({
            "data1": [1., None, np.nan, float("nan"), 50.],
            "flag1": [0, 0, 0, 0, 0],
            "data2": [10., None, np.nan, float("nan"), 50.],
            "flag2": [0, 0, 0, 0, 0]
        })
        self.flag_col_dict = {
            "data1": "flag1",
            "data2": "flag2",
        }


    def test_add_missing_flag(self):
        """Test that add_missing_flag correctly updates the flag column for missing values.
        """
        with patch.dict('dritimeseriesprocessor.__metadata__.config_core_flags.core_flag_config',
                        mock_core_flag_config, clear=True):
            # Call the function
            result = add_missing_flag(self.df, self.flag_col_dict)

            # Expected result
            expected_df = pl.DataFrame({
                "data1": [1., None, np.nan, float("nan"), 50.],
                "flag1": [0, 2, 2, 2, 0],
                "data2": [10., None, np.nan, float("nan"), 50.],
                "flag2": [0, 2, 2, 2, 0]
            })

            # Check if the result matches the expected DataFrame
            self.assertTrue(result.equals(expected_df), "The DataFrames are not equal.")

    def test_no_missing_values(self):
        """Test behavior when there are no missing values in the data column."""
        df_no_missing = pl.DataFrame({
            "data1": [1, 2, 3, 4, 5],
            "flag1": [0, 0, 0, 0, 0],
            "data2": [10, 20, 30, 40, 50],
            "flag2": [0, 0, 0, 0, 0]
        })
        result = add_missing_flag(df_no_missing, self.flag_col_dict)

        # Check if the result matches the expected DataFrame
        self.assertTrue(result.equals(df_no_missing), "The DataFrames should be equal.")

    def test_nonexistent_data_column(self):
        """Test behavior when the specified data column does not exist."""
        with self.assertRaises(pl.exceptions.ColumnNotFoundError):
            add_missing_flag(self.df, {"nonexistent_data": "flag1"})

    def test_nonexistent_flag_column(self):
        """Test behavior when the specified flag column does not exist."""
        with self.assertRaises(pl.exceptions.ColumnNotFoundError):
            add_missing_flag(self.df, {"data1": "nonexistent_flag"})
