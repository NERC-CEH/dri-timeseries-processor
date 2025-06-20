import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime
import polars as pl
from time_stream import TimeSeries

from dritimeseriesprocessor.metrics_exporter import metrics
from dritimeseriesprocessor.processor import (
    load_data_for_group,
    prepare_data_to_load,
    merge_data,
    process_timeseries,
)

# Setup metrics
# -------------
metrics.setup_metrics()


def mock_query_by_date_range(bucket_name, prefix, start_date, end_date, site_ids, columns):
    # Mocking the query to return a DataFrame with dummy data
    data = {
        "SITE_ID": [site_ids[0]] * 3,
        "time": [datetime(2023, 1, 1), datetime(2023, 1, 2), datetime(2023, 1, 3)],
    }
    for column in columns:
        data[column] = [1, 2, 3]

    # Create a DataFrame with the specified columns
    return pl.DataFrame(data)


class TestLoadData(unittest.TestCase):
    def setUp(self):
        self.all_timeseries_ids_metadata = {
            "ts1": {"sourceDataset": "dataset1", "sourceBucket": "bucket1", "sourceColumnName": "col1"},
            "ts2": {"sourceDataset": "dataset1", "sourceBucket": "bucket1", "sourceColumnName": "col2"},
            "ts3": {"sourceDataset": "dataset1", "sourceBucket": "bucket2", "sourceColumnName": "col3"},
            "ts4": {"sourceDataset": "dataset2", "sourceBucket": "bucket1", "sourceColumnName": "col4"},
            "ts5": {"sourceDataset": "dataset2", "sourceBucket": "bucket2", "sourceColumnName": "col5"},
        }

        self.start_date = datetime(2023, 1, 1)
        self.end_date = datetime(2023, 1, 31)

    @patch("dritimeseriesprocessor.processor.data_manager.query_by_date_range")
    @patch("dritimeseriesprocessor.processor.add_processing_dependencies")
    def test_load_data_for_single_dataset_and_bucket(self, mock_deps, mock_query):
        """Test the load_data_for_group where ts_ids are from the same dataset and bucket.
        """
        ts_ids = ["ts1", "ts2"]
        ts_metadata = {ts_id: self.all_timeseries_ids_metadata[ts_id] for ts_id in ts_ids}
        site_id = "site1"

        mock_query.side_effect = mock_query_by_date_range
        mock_deps.side_effect = lambda x: x

        result = load_data_for_group(ts_metadata, site_id, self.start_date, self.end_date)
        self.assertIsInstance(result, pl.DataFrame)
        self.assertEqual(result.shape, (3, 4))

    @patch("dritimeseriesprocessor.processor.data_manager.query_by_date_range")
    @patch("dritimeseriesprocessor.processor.add_processing_dependencies")
    def test_load_data_for_multi_datasets_and_buckets(self, mock_deps, mock_query):
        """Test the load_data_for_group where ts_ids are from multiple datasets and buckets.
        """
        ts_ids = ["ts1", "ts2", "ts3", "ts4", "ts5"]
        ts_metadata = {ts_id: self.all_timeseries_ids_metadata[ts_id] for ts_id in ts_ids}
        site_id = "site1"

        mock_query.side_effect = mock_query_by_date_range
        mock_deps.side_effect = lambda x: x

        result = load_data_for_group(ts_metadata, site_id, self.start_date, self.end_date)
        self.assertIsInstance(result, pl.DataFrame)
        self.assertEqual(result.shape, (3, 7))

    @patch("dritimeseriesprocessor.processor.data_manager.query_by_date_range")
    @patch("dritimeseriesprocessor.processor.add_processing_dependencies")
    def test_no_data(self, mock_deps, mock_query):
        """Test when no data is returned from the query.
        """
        ts_ids = ["ts1", "ts2"]
        ts_metadata = {ts_id: self.all_timeseries_ids_metadata[ts_id] for ts_id in ts_ids}
        site_id = "site1"

        mock_query.return_value = pl.DataFrame()
        mock_deps.side_effect = lambda x: x

        result = load_data_for_group(ts_metadata, site_id, self.start_date, self.end_date)
        self.assertEqual(result, None)


class TestProcessTimeseries(unittest.TestCase):
    @patch("dritimeseriesprocessor.processor.add_initial_core_flags")
    @patch("dritimeseriesprocessor.processor.run_preprocess")
    @patch("dritimeseriesprocessor.processor.run_quality_control")
    @patch("dritimeseriesprocessor.processor.run_infilling")
    def test_process_timeseries(
        self, mock_run_infilling, mock_run_quality_control, mock_run_preprocess, mock_add_initial_core_flags
    ):
        """Test the process_timeseries function.
        """
        ts = MagicMock(spec=TimeSeries)
        ts_metadata = {"ts1": {}, "ts2": {}}

        mock_add_initial_core_flags.return_value = ts
        mock_run_preprocess.return_value = ts
        mock_run_quality_control.return_value = ts
        mock_run_infilling.return_value = ts

        result = process_timeseries(ts, ts_metadata)
        self.assertEqual(result, ts)
        mock_add_initial_core_flags.assert_called_once()
        mock_run_preprocess.assert_called_once()
        mock_run_quality_control.assert_called_once()
        mock_run_infilling.assert_called_once()


if __name__ == "__main__":
    unittest.main()