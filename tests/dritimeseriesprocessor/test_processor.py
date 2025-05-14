import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime
import polars as pl
from time_stream import TimeSeries

from dritimeseriesprocessor.processor import (
    load_data_for_group,
    prepare_data_to_load,
    handle_no_data_case,
    add_processing_dependencies,
    merge_data,
    process_timeseries,
)


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


class TestLoadDataForGroup(unittest.TestCase):
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
        

class TestPrepareDataToLoad(unittest.TestCase):
    def setUp(self):
        self.all_timeseries_ids_metadata = {
            "ts1": {"sourceDataset": "dataset1", "sourceBucket": "bucket1", "sourceColumnName": "col1"},
            "ts2": {"sourceDataset": "dataset1", "sourceBucket": "bucket1", "sourceColumnName": "col2"},
            "ts3": {"sourceDataset": "dataset1", "sourceBucket": "bucket2", "sourceColumnName": "col1"},
            "ts4": {"sourceDataset": "dataset2", "sourceBucket": "bucket1", "sourceColumnName": "col2"},
            "ts5": {"sourceDataset": "dataset2", "sourceBucket": "bucket2", "sourceColumnName": "col2"},
        }

    def test_single_bucket_and_dataset(self):
        """Test the prepare_data_to_load function with a single dataset and bucket."""
        ts_ids = ["ts1", "ts2"]
        ts_metadata = {ts_id: self.all_timeseries_ids_metadata[ts_id] for ts_id in ts_ids}
        result = prepare_data_to_load(ts_metadata)

        expected = {
            "dataset1": {
                "bucket1": {"columns": {"col1", "col2"}}
            }
        }
        self.assertEqual(result, expected)
    
    def test_multiple_buckets_and_datasets(self):
        """Test the prepare_data_to_load function with multiple datasets and buckets."""
        ts_ids = ["ts1", "ts2", "ts3", "ts4", "ts5"]
        ts_metadata = {ts_id: self.all_timeseries_ids_metadata[ts_id] for ts_id in ts_ids}
        result = prepare_data_to_load(ts_metadata)

        expected = {
            "dataset1": {
                "bucket1": {"columns": {"col1", "col2"}},
                "bucket2": {"columns": {"col1"}}
            },
            "dataset2": {
                "bucket1": {"columns": {"col2"}},
                "bucket2": {"columns": {"col2"}}
            }
        }
        self.assertEqual(result, expected)

    def test_repeated_columns(self):
        ts_metadata = {
            "ts1": {"sourceDataset": "dataset1", "sourceBucket": "bucket1", "sourceColumnName": "col1"},
            "ts2": {"sourceDataset": "dataset1", "sourceBucket": "bucket1", "sourceColumnName": "col1"},
        }

        result = prepare_data_to_load(ts_metadata)
        expected = {
            "dataset1": {
                "bucket1": {"columns": {"col1"}}
            }
        }
        self.assertEqual(result, expected)


class TestHandleNoDataCase(unittest.TestCase):
    @patch("dritimeseriesprocessor.processor.metrics.record_no_data_run")
    @patch("dritimeseriesprocessor.processor.metrics.export_metrics_to_pushgateway")
    def test_handle_no_data_case(self, mock_export_metrics, mock_record_no_data_run):
        handle_no_data_case()
        mock_record_no_data_run.assert_called_once()
        mock_export_metrics.assert_called_once()


class TestMergeData(unittest.TestCase):
    def setUp(self):
        self.existing_data = pl.DataFrame({
            "time": [datetime(2023, 1, 1), datetime(2023, 1, 2)],
            "col1": [1, 2],
            "col2": [3, 4]
        })

    def test_simple_merge(self):
        """Test the merge_data function with a simple case."""
        new_data = pl.DataFrame({
            "time": [datetime(2023, 1, 1), datetime(2023, 1, 2)],
            "col1": [1, 2],
            "col3": [5, 6]
        })
        result = merge_data(self.existing_data, new_data)
        self.assertIn("col3", result.columns)
        self.assertEqual(result.shape, (2, 4))

    def test_larger_new_data(self):
        """Test the merge_data function with larger new data."""
        new_data = pl.DataFrame({
            "time": [datetime(2023, 1, 1), datetime(2023, 1, 2), datetime(2023, 1, 3)],
            "col4": [7, 8, 9]
        })
        result = merge_data(self.existing_data, new_data)
        self.assertIn("col4", result.columns)
        self.assertEqual(result.shape, (3, 4))

    def test_no_data(self):
        """Test the merge_data function with no data."""
        new_data = pl.DataFrame()
        result = merge_data(self.existing_data, new_data)
        self.assertEqual(result.columns, ["time", "col1", "col2"])
        self.assertEqual(result.shape, (2, 3))

    def test_differing_column_data(self):
        """Test the merge_data function fails when matching columns have differing data."""
        new_data = pl.DataFrame({
            "time": [datetime(2023, 1, 1), datetime(2023, 1, 2)],
            "col1": [10, 2]
        })
        with self.assertRaises(ValueError):
            merge_data(self.existing_data, new_data)

    def test_all_matching_columns_all_the_same(self):
        """Test the merge_data function fails when all matching columns have repeated data."""
        existing_data = pl.DataFrame({
            "SITE_ID": ["site1", "site1"],
            "col2": [3, 4]
        })
        new_data = pl.DataFrame({
            "SITE_ID": ["site1", "site1"],
            "col3": [1, 2]
        })
        with self.assertRaises(ValueError):
            merge_data(existing_data, new_data)


class TestProcessTimeseries(unittest.TestCase):
    @patch("dritimeseriesprocessor.processor.add_initial_core_flags")
    @patch("dritimeseriesprocessor.processor.run_preprocess")
    @patch("dritimeseriesprocessor.processor.run_quality_control")
    @patch("dritimeseriesprocessor.processor.run_infilling")
    def test_process_timeseries(
        self, mock_run_infilling, mock_run_quality_control, mock_run_preprocess, mock_add_initial_core_flags
    ):
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