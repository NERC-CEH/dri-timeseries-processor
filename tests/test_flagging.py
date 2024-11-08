import unittest
from unittest.mock import patch
from datetime import datetime
import polars as pl

from time_series import TimeSeries
from dritimeseriesprocessor.flagging import initialise_core_flags

class TestInitialiseCoreFlags(unittest.TestCase):
    def setUp(self):
        """Set up a mock core_flag_config for testing."""
        self.mock_core_flag_config = {
            "unchecked": {
                "id": 1  # Mock value for the 'unchecked' flag
            }
        }

    def test_initialise_core_flags(self):
        """Test that initialise_core_flags adds flag columns correctly.
        """
        with patch.dict('dritimeseriesprocessor.__metadata__.config_core_flags.core_flag_config', 
                        self.mock_core_flag_config, clear=True):
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
            self.assertTrue(all(result.df["data_col1_FLAG"] == 1))
            self.assertTrue(all(result.df["data_col2_FLAG"] == 1))

    def test_initialise_core_flags_no_columns(self):
        """Test that an empty DataFrame does not add any flag columns.
        """
        with patch.dict('dritimeseriesprocessor.__metadata__.config_core_flags.core_flag_config', 
                        self.mock_core_flag_config, clear=True):
            # Create a DataFrame with only a time column (no data columns)
            df = pl.DataFrame({
                "time": [datetime(2024, 1, 1), datetime(2024, 1, 2), datetime(2024, 1, 3)]
            })
            ts = TimeSeries.from_polars(df, "time")

            # Call the function
            result = initialise_core_flags(ts)

            # Ensure no flag columns are added
            self.assertEqual(result.df.columns, ["time"])
