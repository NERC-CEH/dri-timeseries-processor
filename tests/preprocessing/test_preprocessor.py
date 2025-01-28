import unittest
from datetime import datetime
from unittest.mock import Mock, patch
import numpy as np
import polars as pl
from polars.testing import assert_frame_equal

from time_series import TimeSeries, Period
from dritimeseriesprocessor.preprocessing.preprocessor import pr_flag_column_name, run_preprocess


class TestPRFlagColumnName(unittest.TestCase):
    """Unit tests for the pr_flag_column_name function.
    """
    def test_standard_column_name(self):
        """
        Test that the function correctly appends '_PRFLAG' to a standard column name.
        """
        self.assertEqual(pr_flag_column_name('data'), 'data_PRFLAG')


class TestRunPreprocessing(unittest.TestCase):
    """
    Test suite for the run_preprocessing function.
    """

    def setUp(self):
        """
        Set up common test data and mocks.
        """
        data = pl.DataFrame({
            'time': [
                datetime(2023, 8, 10),
                datetime(2023, 8, 11),
                datetime(2023, 8, 12),
                datetime(2023, 8, 13),
                datetime(2023, 8, 14),
            ],
            "SITE_ID": ["site1"] * 5,
            'temperature': [20.0, 22.0, 21.0, 20.0, 19.0],
            'humidity': [50, 55, None, None, 60]
        })

        resolution = Period.of_days(1)
        periodicity = Period.of_days(1)
        self.ts = TimeSeries(
            data,
            "time",
            resolution,
            periodicity
        )

        self.mock_methods = [
            Mock(
                method_id="ADD",
                id=1,
            ),
            Mock(
                method_id="MULTIPLY",
                id=2,
            ),
        ]


    @patch("dritimeseriesprocessor.preprocessing.preprocessor.preprocessing_config")
    def test_run_preprocessing_basic(self, mock_preprocessing_config):
        """
        Test basic functionality of run_preprocessing.
        Checks if the function adds the flag system, adds the flag columns, and runs the correction method.
        """
        correction_config = [Mock(
            site_id="site1",
            method_id="ADD",
            variable="temperature",
            start_datetime=datetime(2023, 8, 11),
            end_datetime=datetime(2023, 8, 13),
            correction_factor=10.
        )]

        mock_preprocessing_config.correction_methods = self.mock_methods
        mock_preprocessing_config.corrections = correction_config

        result = run_preprocess(self.ts)

        # Check flag system added
        self.assertIn('pr_flags', result.flag_systems)
        # Check columns added
        self.assertIn('temperature_PRFLAG', result.columns)
        # Check the correction method has been applied
        self.assertEqual(result.df['temperature'].to_list(), [20.0, 32.0, 31.0, 30.0, 19.0])
        # Check flag values have been added
        self.assertEqual(result.df['temperature_PRFLAG'].to_list(), [0, 1, 1, 1, 0])

    @patch("dritimeseriesprocessor.preprocessing.preprocessor.preprocessing_config")
    def test_run_preprocessing_no_config(self, mock_preprocessing_config):
        """
        Test run_preprocessing when no preprocessing config is available.
        Checks if the function returns the original DataFrame unchanged.
        """
        mock_preprocessing_config.correction_methods = self.mock_methods
        mock_preprocessing_config.corrections = []

        result = run_preprocess(self.ts)

        assert_frame_equal(result.df, self.ts.df)

    @patch("dritimeseriesprocessor.preprocessing.preprocessor.preprocessing_config")
    def test_run_preprocessing_no_methods(self, mock_preprocessing_config):
        """
        Test run_preprocessing when preprocessing config exists but no methods are specified.
        Checks if the function returns the original DataFrame unchanged.
        """
        correction_config = Mock(
            site_id="site1",
            method_id="ADD",
            variable="temperature",
            start_datetime=datetime(2023, 8, 11),
            end_datetime=datetime(2023, 8, 13),
            correction_factor=10.
        )

        mock_preprocessing_config.correction_methods = []
        mock_preprocessing_config.corrections = [correction_config]

        result = run_preprocess(self.ts)

        assert_frame_equal(result.df, self.ts.df)

    @patch("dritimeseriesprocessor.preprocessing.preprocessor.preprocessing_config")
    def test_run_preprocessing_multiple_methods(self, mock_preprocessing_config):
        """
        Test run_preprocessing with multiple preprocessing methods for a single column.
        Checks if the method flags are all applied.
        """
        correction_config = [
            Mock(
                site_id="site1",
                method_id="ADD",
                variable="temperature",
                start_datetime=datetime(2023, 8, 11),
                end_datetime=datetime(2023, 8, 13),
                correction_factor=10.
            ),
            Mock(
                site_id="site1",
                method_id="MULTIPLY",
                variable="temperature",
                start_datetime=datetime(2023, 8, 10),
                end_datetime=datetime(2023, 8, 12),
                correction_factor=2.
            ),
        ]

        mock_preprocessing_config.correction_methods = self.mock_methods
        mock_preprocessing_config.corrections = correction_config

        result = run_preprocess(self.ts)

        # Check the correction method has been applied
        self.assertEqual(result.df['temperature'].to_list(), [40.0, 64.0, 62.0, 30.0, 19.0])
        # Check flag values have been added
        self.assertEqual(result.df['temperature_PRFLAG'].to_list(), [2, 3, 3, 1, 0])

    @patch("dritimeseriesprocessor.preprocessing.preprocessor.preprocessing_config")
    def test_run_preprocessing_end_date_is_none(self, mock_preprocessing_config):
        """
        Test end_date is None in config leads to all dates after start dat being corrected.

        """
        correction_config = [Mock(
            site_id="site1",
            method_id="ADD",
            variable="temperature",
            start_datetime=datetime(2023, 8, 11),
            end_datetime=None,
            correction_factor=10.
        )]

        mock_preprocessing_config.correction_methods = self.mock_methods
        mock_preprocessing_config.corrections = correction_config

        result = run_preprocess(self.ts)

        # Check the correction method has been applied
        self.assertEqual(result.df['temperature'].to_list(), [20.0, 32.0, 31.0, 30.0, 29.0])
        # Check flag values have been added
        self.assertEqual(result.df['temperature_PRFLAG'].to_list(), [0, 1, 1, 1, 1])
