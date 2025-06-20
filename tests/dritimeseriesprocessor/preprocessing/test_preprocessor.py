import unittest
from datetime import datetime
from unittest.mock import Mock, patch
import polars as pl
from polars.testing import assert_frame_equal

from time_stream import TimeSeries, Period
from dritimeseriesprocessor.flagging.flagger import add_initial_core_flags
from dritimeseriesprocessor.preprocessing.preprocessor import run_preprocess


class TestRunPreprocessing(unittest.TestCase):
    """
    Test suite for the run_preprocessing function.
    """

    def setUp(self):
        """
        Set up common test data and mocks.
        """
        ta_data = pl.DataFrame({
            'time': [
                datetime(2023, 8, 10),
                datetime(2023, 8, 11),
                datetime(2023, 8, 12),
                datetime(2023, 8, 13),
                datetime(2023, 8, 14),
            ],
            'temperature': [20.0, 22.0, 21.0, 20.0, 19.0]
        })
        rh_data = pl.DataFrame({
            'time': [
                datetime(2023, 8, 10),
                datetime(2023, 8, 11),
                datetime(2023, 8, 12),
                datetime(2023, 8, 13),
                datetime(2023, 8, 14),
            ],
            'humidity': [50, 55, None, None, 60]
        })

        resolution = Period.of_days(1)
        periodicity = Period.of_days(1)

        ta_ts = TimeSeries(
            ta_data,
            "time",
            resolution,
            periodicity,
            metadata={"site_id": "site1"}
        )
        ta_ts = add_initial_core_flags(ta_ts)

        rh_ts = TimeSeries(
            rh_data,
            "time",
            resolution,
            periodicity,
            metadata={"site_id": "site1"}
        )
        rh_ts = add_initial_core_flags(rh_ts)

        self.ta_ts_id = "site1_temperature_1d_raw"
        self.rh_ts_id = "site1_humidity_1d_raw"

        self.ts_ids = {
            self.ta_ts_id: {
                "data": ta_ts,
                # "sourceSite": "site1",
                # "sourceColumnName": "temperature",
                # "sourceDataset": "dataset1",
                # "sourceBucket": "bucket1",
                # "resolution": resolution,
                # "periodicity": periodicity,
            },
            self.rh_ts_id: {
                "data": rh_ts,
                # "sourceSite": "site1",
                # "sourceColumnName": "humidity",
                # "sourceDataset": "dataset1",
                # "sourceBucket": "bucket1",
                # "resolution": resolution,
                # "periodicity": periodicity,
            }
        }

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

        result = run_preprocess(self.ts_ids)

        # Check flag system added
        self.assertIn('pr_flags', result[self.ta_ts_id]["data"].flag_systems)
        # Check columns added
        self.assertIn('temperature_PR_FLAG', result[self.ta_ts_id]["data"].columns)
        # Check the correction method has been applied
        self.assertEqual(result[self.ta_ts_id]["data"].df['temperature'].to_list(), [20.0, 32.0, 31.0, 30.0, 19.0])
        # Check flag values have been added
        self.assertEqual(result[self.ta_ts_id]["data"].df['temperature_PR_FLAG'].to_list(), [0, 1, 1, 1, 0])

    @patch("dritimeseriesprocessor.preprocessing.preprocessor.preprocessing_config")
    def test_run_preprocessing_no_config(self, mock_preprocessing_config):
        """
        Test run_preprocessing when no preprocessing config is available.
        Checks if the function returns the original DataFrame unchanged.
        """
        mock_preprocessing_config.correction_methods = self.mock_methods
        mock_preprocessing_config.corrections = []

        result = run_preprocess(self.ts_ids)

        self.assertEqual(result, self.ts_ids)

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

        result = run_preprocess(self.ts_ids)

        self.assertEqual(result, self.ts_ids)

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

        result = run_preprocess(self.ts_ids)

        # Check the correction method has been applied
        self.assertEqual(result[self.ta_ts_id]["data"].df['temperature'].to_list(), [40.0, 64.0, 62.0, 30.0, 19.0])
        # Check flag values have been added
        self.assertEqual(result[self.ta_ts_id]["data"].df['temperature_PR_FLAG'].to_list(), [2, 3, 3, 1, 0])

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

        result = run_preprocess(self.ts_ids)

        # Check the correction method has been applied
        self.assertEqual(result[self.ta_ts_id]["data"].df['temperature'].to_list(), [20.0, 32.0, 31.0, 30.0, 29.0])
        # Check flag values have been added
        self.assertEqual(result[self.ta_ts_id]["data"].df['temperature_PR_FLAG'].to_list(), [0, 1, 1, 1, 1])
