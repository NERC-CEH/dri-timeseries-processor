import unittest
from unittest.mock import patch, MagicMock

from datetime import datetime
import polars as pl
import numpy as np

from time_series import TimeSeries
from dritimeseriesprocessor.flagging import (
    initialise_core_flags,
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
            self.assertTrue(all(result.df["data_col1_FLAG"] == 1))
            self.assertTrue(all(result.df["data_col2_FLAG"] == 1))

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


class TestAddUncheckedFlag(unittest.TestCase):
    """Unit tests for the add_unchecked_flag function."""

    def setUp(self):
        """Set up a sample DataFrame for testing."""
        self.df = pl.DataFrame({
            "data": [10, 20, 30],
            "flag": [0, 0, 0]  # Initial flag values
        })

    def test_add_unchecked_flag(self):
        """Test that add_unchecked_flag correctly updates the flag column.
        """
        with patch.dict('dritimeseriesprocessor.__metadata__.config_core_flags.core_flag_config',
                        mock_core_flag_config, clear=True):
            # Call the function
            result = add_unchecked_flag(self.df, "flag")

            # Expected result
            expected_df = pl.DataFrame({
                "data": [10, 20, 30],
                "flag": [1, 1, 1]  # All values in the flag column should be updated to 1
            })

            # Check if the result matches the expected DataFrame
            self.assertTrue(result.equals(expected_df), "The DataFrames are not equal.")

    def test_nonexistent_flag_column(self):
        """Test behavior when the specified flag column does not exist."""
        with self.assertRaises(pl.exceptions.ColumnNotFoundError):
            add_unchecked_flag(self.df, "nonexistent_flag")


class TestAddMissingFlag(unittest.TestCase):
    """Unit tests for the add_missing_flag function."""

    def setUp(self):
        """Set up a sample DataFrame for testing."""
        self.df = pl.DataFrame({
            "data": [10., None, np.nan, float("nan"), 50.],
            "flag": [0, 0, 0, 0, 0]  # Initial flag values
        })


    def test_add_missing_flag(self):
        """Test that add_missing_flag correctly updates the flag column for missing values.
        """
        with patch.dict('dritimeseriesprocessor.__metadata__.config_core_flags.core_flag_config',
                        mock_core_flag_config, clear=True):
            # Call the function
            result = add_missing_flag(self.df, "data", "flag")

            # Expected result
            expected_df = pl.DataFrame({
                "data": [10., None, np.nan, float("nan"), 50.],
                "flag": [0, 2, 2, 2, 0]  # Flags updated for missing values
            })

            # Check if the result matches the expected DataFrame
            self.assertTrue(result.equals(expected_df), "The DataFrames are not equal.")

    def test_no_missing_values(self):
        """Test behavior when there are no missing values in the data column."""
        df_no_missing = pl.DataFrame({
            "data": [10, 20, 30, 40, 50],
            "flag": [0, 0, 0, 0, 0]
        })
        result = add_missing_flag(df_no_missing, "data", "flag")

        # Expected result should be the same as input
        expected_df = df_no_missing

        # Check if the result matches the expected DataFrame
        self.assertTrue(result.equals(expected_df), "The DataFrames should be equal.")

    def test_nonexistent_data_column(self):
        """Test behavior when the specified data column does not exist."""
        with self.assertRaises(pl.exceptions.ColumnNotFoundError):
            add_missing_flag(self.df, "nonexistent_data", "flag")

    def test_nonexistent_flag_column(self):
        """Test behavior when the specified flag column does not exist."""
        with self.assertRaises(pl.exceptions.ColumnNotFoundError):
            add_missing_flag(self.df, "data", "nonexistent_flag")
