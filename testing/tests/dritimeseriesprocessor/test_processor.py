import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime
import polars as pl
from time_stream import TimeSeries

from dritimeseriesprocessor.metrics_exporter import metrics
from dritimeseriesprocessor.processor import (
    load_data,
    shift_processed_data,
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


def mock_query_by_date_range_no_data(bucket_name, prefix, start_date, end_date, site_ids, columns):
    # An empty dataframe with the specified columns should be returned.
    data = {"time": []}
    schema = {"time": pl.Datetime(time_unit='us', time_zone="UTC")}
    
    for column in columns:
        data[column] = []
        schema[column] = pl.Int64

    return pl.DataFrame(data, schema)


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
    def test_load_data_for_no_data(self, mock_query):
        """Test the load_data when there is no data.
        """
        mock_query.side_effect = mock_query_by_date_range_no_data

        result = load_data(self.ts_metadata, self.start_date, self.end_date)
        self.assertIsInstance(result, TimeSeries)
        self.assertEqual(result.df.shape, (0, 2))


class TestShiftProcessedData(unittest.TestCase):
    def test_expected_shift(self):
        ts_ids = {
            "ts1_raw": {
                "data": [1],
            },
            "ts2_processed": {
                "method_type": "process",
                "inputs": ["ts1_raw"]
            }
        }

        expected = {
            "ts1_raw": {
            },
            "ts2_processed": {
                "data": [1],
                "method_type": "process",
                "inputs": ["ts1_raw"]
            }
        }

        result = shift_processed_data(ts_ids)
        self.assertEqual(result, expected)


@unittest.skip("Skipped until FPM-510 is fixed")
class TestProcessTimeseries(unittest.TestCase):

    @patch("dritimeseriesprocessor.processor.run_corrections")
    @patch("dritimeseriesprocessor.processor.run_quality_control")
    @patch("dritimeseriesprocessor.processor.run_infilling")
    def test_process_timeseries(
        self, mock_run_infilling, mock_run_quality_control, mock_run_corrections
    ):
        """Test the process_timeseries function.
        """
        ts_metadata = {
            "ts1_raw": {
                "data": [1],
            },
            "ts2_processed": {
                "method_type": "process",
                "inputs": ["ts1_raw"]
            }
        }
        return_ts_metadata = {
            "ts1_raw": {
                "data": [2],
            },
            "ts2_processed": {
                "method_type": "process",
                "inputs": ["ts1_raw"]
            }
        }
        expected = {
            "ts1_raw": {
            },
            "ts2_processed": {
                "data": [2],
                "method_type": "process",
                "inputs": ["ts1_raw"]
            }
        }

        mock_run_corrections.return_value = return_ts_metadata
        mock_run_quality_control.return_value = return_ts_metadata
        mock_run_infilling.return_value = return_ts_metadata

        result = process_timeseries(ts_metadata)
        self.assertEqual(result, expected)
        mock_run_corrections.assert_called_once()
        mock_run_quality_control.assert_called_once()
        mock_run_infilling.assert_called_once()


if __name__ == "__main__":
    unittest.main()