import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime
import polars as pl
from time_stream import TimeSeries

from dritimeseriesprocessor.metrics_exporter import metrics
from dritimeseriesprocessor.processor import (
    load_data,
    process_timeseries,
)

# Setup metrics
# -------------
metrics.setup_metrics()


def mock_query_by_date_range(bucket_name, prefix, start_date, end_date, site_ids, columns):
    # Mocking the query to return a DataFrame with dummy data
    data = {
        "time": [datetime(2023, 1, 1), datetime(2023, 1, 2), datetime(2023, 1, 3)],
    }
    for column in columns:
        data[column] = [1, 2, 3]

    # Create a DataFrame with the specified columns
    return pl.DataFrame(data)


def mock_query_by_date_range_no_cols(bucket_name, prefix, start_date, end_date, site_ids, columns):
    # Return an empty DataFrame when no valid columns are provided
    return pl.DataFrame({})


class TestLoadData(unittest.TestCase):
    def setUp(self):
        self.ts_metadata = {
            "sourceDataset": "dataset1",
            "sourceBucket": "bucket1",
            "sourceColumnName": "col1",
            "sourceSite": "site1",
            "resolution": "PT30M",
            "periodicity": "PT30M",
            "processing_level": "raw",
        }

        self.start_date = datetime(2023, 1, 1)
        self.end_date = datetime(2023, 1, 31)

    @patch("dritimeseriesprocessor.processor.data_manager.query_by_date_range")
    def test_load_data_success(self, mock_query):
        """Test the load_data with valid ts_id.
        """
        mock_query.side_effect = mock_query_by_date_range

        result = load_data(self.ts_metadata, self.start_date, self.end_date)
        self.assertIsInstance(result, TimeSeries)
        self.assertEqual(result.df.shape, (3, 2))

    @patch("dritimeseriesprocessor.processor.data_manager.query_by_date_range")
    def test_load_data_for_no_cols(self, mock_query):
        """Test the load_data when there are no valid columns.
        """
        mock_query.side_effect = mock_query_by_date_range_no_cols

        result = load_data(self.ts_metadata, self.start_date, self.end_date)
        self.assertEqual(result, None)


class TestProcessTimeseries(unittest.TestCase):

    @patch("dritimeseriesprocessor.processor.run_preprocess")
    @patch("dritimeseriesprocessor.processor.run_quality_control")
    @patch("dritimeseriesprocessor.processor.run_infilling")
    def test_process_timeseries(
        self, mock_run_infilling, mock_run_quality_control, mock_run_preprocess
    ):
        """Test the process_timeseries function.
        """
        ts = MagicMock(spec=TimeSeries)
        ts_metadata = {"ts1": {}, "ts2": {}}

        mock_run_preprocess.return_value = ts
        mock_run_quality_control.return_value = ts
        mock_run_infilling.return_value = ts

        result = process_timeseries(ts_metadata)
        self.assertEqual(result, ts)
        mock_run_preprocess.assert_called_once()
        mock_run_quality_control.assert_called_once()
        mock_run_infilling.assert_called_once()


if __name__ == "__main__":
    unittest.main()