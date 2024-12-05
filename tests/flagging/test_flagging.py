import unittest
from unittest.mock import patch, MagicMock

from datetime import datetime
import polars as pl
from polars.testing import assert_frame_equal
import numpy as np

from time_series import TimeSeries
from dritimeseriesprocessor.flagging.flagger import (
    core_flag_column_name,
    initialise_core_flags,
    quality_control_core_flags,
    add_unchecked_flag,
    remove_unchecked_flag,
    add_missing_flag,
    add_removed_flag
)


mock_core_flag_config = {
    "unchecked": MagicMock(id=1),
    "missing": MagicMock(id=2),
    "removed": MagicMock(id=4),
}


class TestCoreFlagColumnName(unittest.TestCase):
    """Unit tests for the core_flag_column_name function.
    """
    def test_standard_column_name(self):
        """
        Test that the function correctly appends '_FLAG' to a standard column name.
        """
        self.assertEqual(core_flag_column_name('data'), 'data_FLAG')


class TestInitialiseCoreFlags(unittest.TestCase):

    def test_initialise_core_flags(self):
        """Test that initialise_core_flags adds flag columns correctly.
        """
        with patch.dict('dritimeseriesprocessor.__metadata__.config_core_flags.core_flag_config', 
                        mock_core_flag_config, clear=True):
            df = pl.DataFrame({
                "time": [datetime(2024, 1, 1), datetime(2024, 1, 2), datetime(2024, 1, 3)],
                "data_col1": [1, 2, 3],
                "data_col2": [1, 2, 3]
            })
            ts = TimeSeries(df, "time")
            initialise_core_flags(ts)
            self.assertEqual(ts.columns, ["data_col1", "data_col1_FLAG", "data_col2", "data_col2_FLAG"])
            self.assertEqual(ts.supplementary_columns, ["data_col1_FLAG", "data_col2_FLAG"])
            self.assertEqual(ts.data_columns, ["data_col1", "data_col2"])

    def test_initialise_core_flags_no_columns(self):
        """Test that an empty DataFrame does not add any flag columns.
        """
        with patch.dict('dritimeseriesprocessor.__metadata__.config_core_flags.core_flag_config', 
                        mock_core_flag_config, clear=True):
            # Create a DataFrame with only a time column (no data columns)
            df = pl.DataFrame({
                "time": [datetime(2024, 1, 1), datetime(2024, 1, 2), datetime(2024, 1, 3)]
            })
            ts = TimeSeries(df, "time")

            # Call the function
            result = initialise_core_flags(ts)

            # Ensure no flag columns are added
            self.assertEqual(result.df.columns, ["time"])


class TestQualityControlCoreFlags(unittest.TestCase):
    """Unit tests for the quality_control_core_flags function.
    """
    @patch('dritimeseriesprocessor.flagging.flagger.core_flag_column_name')
    @patch('dritimeseriesprocessor.quality_control.utils.qc_flag_column_name')
    def test_quality_control_core_flags(self, mock_qc_flag_column_name, mock_core_flag_column_name):
        """
        Test that quality_control_core_flags correctly processes the TimeSeries object.
        """
        mock_qc_flag_column_name.return_value = "data_QCFLAG"
        mock_core_flag_column_name.return_value = "data_FLAG"

        df = pl.DataFrame({
                "time": [datetime(2024, 1, 1), datetime(2024, 1, 2), datetime(2024, 1, 3)],
                "data": [1, None, None],
                "data_QCFLAG": [0, 2, 3],
                "data_FLAG": [1, 1, 1],
            })
        ts = TimeSeries(df, "time", supplementary_columns=["data_QCFLAG", "data_FLAG"])

        expected_df = pl.DataFrame({
                "time": [datetime(2024, 1, 1), datetime(2024, 1, 2), datetime(2024, 1, 3)],
                "data": [1, None, None],
                "data_QCFLAG": [0, 2, 3],
                "data_FLAG": [0, 4, 4],
            })
        expected = TimeSeries(expected_df, "time", supplementary_columns=["data_QCFLAG", "data_FLAG"])

        with patch.dict('dritimeseriesprocessor.__metadata__.config_core_flags.core_flag_config',
                        mock_core_flag_config, clear=True):
            result = quality_control_core_flags(ts)
            assert_frame_equal(result.df, expected.df)


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


class TestRemoveUncheckedFlag(unittest.TestCase):
    """Unit tests for the remove_unchecked_flag function."""

    def setUp(self):
        """Set up a sample DataFrame for testing."""
        self.df = pl.DataFrame({
            "data1": [1, 2, 3],
            "core_flag1": [1, 5, 1],
            "qc_flag1": [0, 1, 0],
            "data2": [10, 20, 30],
            "core_flag2": [1, 1, 3],
            "qc_flag2": [1, 0, 1],
        })
        self.flag_col_dict = {
            "data1": {"core_flag_col": "core_flag1", "qc_flag_col": "qc_flag1"},
            "data2": {"core_flag_col": "core_flag2", "qc_flag_col": "qc_flag2"},
        }

    def test_remove_unchecked_flag(self):
        """Test that remove_unchecked_flag correctly updates the flag columns."""
        with patch.dict('dritimeseriesprocessor.__metadata__.config_core_flags.core_flag_config',
                        mock_core_flag_config, clear=True):
            # Call the function
            result = remove_unchecked_flag(self.df, self.flag_col_dict)

            # Expected result
            expected_df = pl.DataFrame({
                "data1": [1, 2, 3],
                "core_flag1": [0, 4, 0],
                "qc_flag1": [0, 1, 0],
                "data2": [10, 20, 30],
                "core_flag2": [0, 0, 2],
                "qc_flag2": [1, 0, 1],
            })

            # Check if the result matches the expected DataFrame
            assert_frame_equal(result, expected_df)


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


class TestAddRemovedFlag(unittest.TestCase):
    """Unit tests for the add_removed_flag function."""

    def setUp(self):
        """Set up a sample DataFrame for testing."""
        self.df = pl.DataFrame({
            "data1": [1, None, 3],
            "core_flag1": [0, 0, 0],
            "qc_flag1": [0, 1, 0],
            "data2": [np.nan, np.nan, 30.],
            "core_flag2": [0, 0, 0],
            "qc_flag2": [1, 0, 1],
        })
        self.flag_col_dict = {
            "data1": {"core_flag_col": "core_flag1", "qc_flag_col": "qc_flag1"},
            "data2": {"core_flag_col": "core_flag2", "qc_flag_col": "qc_flag2"},
        }

    def test_add_removed_flag(self):
        """Test that add_removed_flag correctly updates the flag columns."""
        with patch.dict('dritimeseriesprocessor.__metadata__.config_core_flags.core_flag_config',
                        mock_core_flag_config, clear=True):
            # Call the function
            result = add_removed_flag(self.df, self.flag_col_dict)

            # Expected result
            expected_df = pl.DataFrame({
                "data1": [1, None, 3],
                "core_flag1": [0, 4, 0],  # Values should be incremented by flag_val where data is None and qc_flag > 0
                "qc_flag1": [0, 1, 0],
                "data2": [np.nan, np.nan, 30.],
                "core_flag2": [4, 0, 0],  # Values should be incremented by flag_val where data is None and qc_flag > 0
                "qc_flag2": [1, 0, 1],
            })

            # Check if the result matches the expected DataFrame
            assert_frame_equal(result, expected_df)

    def test_no_removed_values(self):
        """Test behavior when there are no removed values in the DataFrame."""
        df_no_removed_values = pl.DataFrame({
            "data1": [1, 2, 3],
            "core_flag1": [0, 0, 0],
            "qc_flag1": [0, 0, 0],
            "data2": [10, 20, 30],
            "core_flag2": [0, 0, 0],
            "qc_flag2": [0, 0, 0],
        })
        result = add_removed_flag(df_no_removed_values, self.flag_col_dict)

        # Check if the result matches the original DataFrame
        assert_frame_equal(result, df_no_removed_values)
