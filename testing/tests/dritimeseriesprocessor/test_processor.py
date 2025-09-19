from datetime import date, datetime
from typing import Union
from unittest.mock import MagicMock, patch

import polars as pl
import pytest
from time_stream import TimeSeries

from dritimeseriesprocessor.metrics_exporter import metrics
from dritimeseriesprocessor.processor import (
    load_data,
    process_timeseries,
    shift_processed_data,
)

# Setup metrics
# -------------
metrics.setup_metrics()


def mock_query_by_date_range(
    bucket_name: str,
    prefix: str,
    start_date: Union[date, datetime],
    end_date: Union[date, datetime, None],
    site_ids: list[str],
    columns: list | str,
) -> pl.DataFrame:
    # Mocking the query to return a DataFrame with dummy data
    data = {
        "time": [datetime(2023, 1, 1), datetime(2023, 1, 2), datetime(2023, 1, 3)],
    }
    for column in columns:
        data[column] = [1, 2, 3]

    # Create a DataFrame with the specified columns
    return pl.DataFrame(data)


def mock_query_by_date_range_no_data(
    bucket_name: str,
    prefix: str,
    start_date: Union[date, datetime],
    end_date: Union[date, datetime, None],
    site_ids: list[str],
    columns: list | str,
) -> pl.DataFrame:
    # An empty dataframe with the specified columns should be returned.
    data = {"time": []}
    schema = {"time": pl.Datetime(time_unit="us", time_zone="UTC")}

    for column in columns:
        data[column] = []
        schema[column] = pl.Int64

    return pl.DataFrame(data, schema)


class TestLoadData:
    ts_metadata = {
        "sourceDataset": "dataset1",
        "sourceBucket": "bucket1",
        "sourceColumnName": "col1",
        "sourceSite": "site1",
        "resolution": "PT30M",
        "periodicity": "PT30M",
        "processing_level": "raw",
    }

    start_date = datetime(2023, 1, 1)
    end_date = datetime(2023, 1, 31)

    @patch("dritimeseriesprocessor.processor.data_manager.query_by_date_range")
    def test_load_data_success(self, mock_query: MagicMock) -> None:
        """Test the load_data with valid ts_id."""
        mock_query.side_effect = mock_query_by_date_range

        result = load_data(self.ts_metadata, self.start_date, self.end_date)
        assert isinstance(result, TimeSeries)
        assert result.df.shape == (3, 2)

    @patch("dritimeseriesprocessor.processor.data_manager.query_by_date_range")
    def test_load_data_for_no_data(self, mock_query: MagicMock) -> None:
        """Test the load_data when there is no data."""
        mock_query.side_effect = mock_query_by_date_range_no_data

        result = load_data(self.ts_metadata, self.start_date, self.end_date)
        assert isinstance(result, TimeSeries)
        assert result.df.shape == (0, 2)


class TestShiftProcessedData:
    def test_expected_shift(self) -> None:
        ts_ids = {
            "ts1_raw": {
                "ts_def": "ts1_raw",
                "sourceSite": "alic1",
                "data": [1],
            },
            "ts2_processed": {"method_type": "process", "sourceSite": "alic1", "inputs": ["ts1_raw"]},
        }

        expected = {
            "ts1_raw": {"ts_def": "ts1_raw", "sourceSite": "alic1"},
            "ts2_processed": {"data": [1], "method_type": "process", "sourceSite": "alic1", "inputs": ["ts1_raw"]},
        }

        result = shift_processed_data(ts_ids)
        assert result == expected


class TestProcessTimeseries:
    @patch("dritimeseriesprocessor.processor.run_corrections")
    @patch("dritimeseriesprocessor.processor.run_quality_control")
    @patch("dritimeseriesprocessor.processor.run_infilling")
    def test_process_timeseries(
        self, mock_run_infilling: MagicMock, mock_run_quality_control: MagicMock, mock_run_corrections: MagicMock
    ) -> None:
        """Test the process_timeseries function."""
        ts_metadata = {
            "ts1_raw": {
                "ts_def": "ts1_raw",
                "sourceSite": "alic1",
                "data": [1],
            },
            "ts2_processed": {"method_type": "process", "sourceSite": "alic1", "inputs": ["ts1_raw"]},
        }
        return_ts_metadata = {
            "ts1_raw": {
                "ts_def": "ts1_raw",
                "sourceSite": "alic1",
                "data": [2],
            },
            "ts2_processed": {"method_type": "process", "sourceSite": "alic1", "inputs": ["ts1_raw"]},
        }
        expected = {
            "ts1_raw": {"ts_def": "ts1_raw", "sourceSite": "alic1"},
            "ts2_processed": {"method_type": "process", "sourceSite": "alic1", "inputs": ["ts1_raw"], "data": [2]},
        }

        mock_run_corrections.return_value = return_ts_metadata
        mock_run_quality_control.return_value = return_ts_metadata
        mock_run_infilling.return_value = return_ts_metadata

        result = process_timeseries(ts_metadata)

        assert result == expected

        mock_run_corrections.assert_called_once()
        mock_run_quality_control.assert_called_once()
        mock_run_infilling.assert_called_once()
