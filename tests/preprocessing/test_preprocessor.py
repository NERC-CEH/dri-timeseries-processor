import unittest
from datetime import datetime
from unittest.mock import Mock, patch

import polars as pl
from polars.testing import assert_frame_equal

from time_series import TimeSeries
from dritimeseriesprocessor.preprocessing.preprocessor import pr_flag_column_name, run_preprocess


class TestPRFlagColumnName(unittest.TestCase):
    """Unit tests for the core_flag_column_name function.
    """
    def test_standard_column_name(self):
        """
        Test that the function correctly appends '_PRFLAG' to a standard column name.
        """
        self.assertEqual(pr_flag_column_name('data'), 'data_PRFLAG')


class TestPreprocess(unittest.TestCase):
    def setUp(self):
        data = pl.DataFrame({
            "SITE_ID": ["site1"] * 6,
            "time": [
                datetime(2023, 8, 10),
                datetime(2023, 8, 11),
                datetime(2023, 8, 12),
                datetime(2023, 8, 13),
                datetime(2023, 8, 14),
                datetime(2023, 8, 15)
            ],
            "value": [10., 20., 30., 40., 50., 60.]
        })
        self.ts = TimeSeries(
            data,
            "time",
        )

    @patch("dritimeseriesprocessor.preprocessing.preprocessor.preprocessing_config")
    def test_preprocess_unimplemented_method(self, mock_preprocessing_config):
        """ Test that preprocess skips unimplemented methods.
        """
        correction_config = Mock(
            METHOD_ID="unknown_method"
        )
        mock_preprocessing_config.corrections = [correction_config]

        with self.assertLogs("dritimeseriesprocessor.preprocessing.preprocessor", level="WARNING") as logs:
            result = run_preprocess(self.ts)
            print(logs.output[0])
            self.assertIn("Unimplemented method: unknown_method", logs.output[0])

        assert_frame_equal(result.df, self.ts.df)

    @patch("dritimeseriesprocessor.preprocessing.preprocessor.preprocessing_config")
    def test_preprocess_variable_not_in_df(self, mock_preprocessing_config):
        """ Test that preprocess skips corrections if the variable is not in DataFrame.
        """
        correction_config = Mock(
            METHOD_ID="ADD",
            VARIABLE="non_existent_column"
        )
        mock_preprocessing_config.corrections = [correction_config]

        with self.assertLogs("dritimeseriesprocessor.preprocessing.preprocessor", level="WARNING") as logs:
            result = run_preprocess(self.ts)
            self.assertIn("Variable non_existent_column not in DataFrame for method ADD", logs.output[0])

        assert_frame_equal(result.df, self.ts.df)

    @patch('dritimeseriesprocessor.preprocessing.preprocessor.datetime')
    @patch("dritimeseriesprocessor.preprocessing.preprocessor.preprocessing_config")
    def test_preprocess_end_date_is_none(self, mock_preprocessing_config, mock_datetime):
        """ Test that the end date is handled it's empty in the config
        """
        correction_config = Mock(
            SITE_ID="site1",
            METHOD_ID="ADD",
            VARIABLE="value",
            START_DATETIME=datetime(2023, 8, 11),
            END_DATETIME=None,
            CORRECTION_FACTOR=10.
        )
        dummy_now = datetime(2024, 1, 1)

        mock_preprocessing_config.corrections = [correction_config]
        mock_datetime.now.return_value = dummy_now

        result = run_preprocess(self.ts)

        # Check the end date has been set to "now"
        self.assertEqual(correction_config.END_DATETIME, dummy_now)

        # Adds 10 to the site 1 data from 11th onwards
        expected_df = pl.DataFrame({
            "SITE_ID": ["site1"] * 6,
            "time": [
                datetime(2023, 8, 10),
                datetime(2023, 8, 11),
                datetime(2023, 8, 12),
                datetime(2023, 8, 13),
                datetime(2023, 8, 14),
                datetime(2023, 8, 15)
            ],
            "value": [10., 30., 40., 50., 60., 70.],
            "value_PRFLAG": [None, 'ADD', 'ADD', 'ADD', 'ADD', 'ADD'],
        })
        expected = TimeSeries(
            expected_df,
            "time",
        )

        assert_frame_equal(result.df, expected.df)
