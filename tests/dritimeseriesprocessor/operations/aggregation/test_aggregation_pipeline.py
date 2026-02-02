from datetime import datetime
from unittest.mock import MagicMock

import polars as pl
import time_stream as ts
from polars.testing import assert_frame_equal
from time_stream.period import Period

from dritimeseriesprocessor.operations.aggregation.aggregation_pipeline import AggregationPipeline


def create_mock_timeframe(col_name: str) -> ts.TimeFrame:
    """Create a mock TimeFrame with necessary attributes."""
    time_vals = [datetime(2025, 1, 1), datetime(2025, 1, 2), datetime(2025, 1, 3)]
    metadata = {"column_name": col_name}
    df = pl.DataFrame({"time": time_vals, col_name: [4, 5, 6]})
    tf = ts.TimeFrame(df, "time").with_metadata(metadata)
    return tf


class TestRenameAggregationColumns:
    def test_rename_columns(self) -> None:
        """Test that rename columns works correctly."""
        input_tf = create_mock_timeframe("value")
        expected = create_mock_timeframe("new_value")

        pipeline = AggregationPipeline()
        result = pipeline._rename_aggregation_columns(input_tf, "new_value", "value")
        assert_frame_equal(result.df, expected.df)

    def test_same_column_name(self) -> None:
        """Test that the same column name passes through unscathed."""
        input_tf = create_mock_timeframe("value")
        expected = create_mock_timeframe("value")

        pipeline = AggregationPipeline()
        result = pipeline._rename_aggregation_columns(input_tf, "value", "value")
        assert_frame_equal(result.df, expected.df)


class TestAggregationThreshold:
    def test_aggregation_threshold_invalid(self) -> None:
        """Check handling of data where the aggregation threshold is not met."""

        df = pl.DataFrame(
            {
                "time": [
                    datetime(2025, 1, 1, 0, 0, 0),
                    datetime(2025, 1, 1, 0, 30, 0),
                    datetime(2025, 1, 1, 1, 0, 0),
                    datetime(2025, 1, 1, 1, 30, 0),
                    datetime(2025, 1, 2, 0, 0, 0),
                    datetime(2025, 1, 2, 0, 30, 0),
                    datetime(2025, 1, 3, 0, 0, 0),
                    datetime(2025, 1, 3, 0, 30, 0),
                ],
                "value": [1, 2, 3, 4, 5, 6, 7, 8],
            }
        )
        input_tf = ts.TimeFrame(df, "time", resolution=Period.of_minutes(30)).with_metadata({"column_name": "value"})

        expected_df = pl.DataFrame(
            {
                "time": [
                    datetime(2025, 1, 1),
                    datetime(2025, 1, 2),
                    datetime(2025, 1, 3),
                ],
                "value": [10, None, None],
                "value_CORE_FLAG": [0, 4, 4],
            }
        )

        container = MagicMock()
        container.data = input_tf
        container.source_column = "value"

        config = MagicMock()
        config.params = {"dep_ts": "ts_1", "aggregation_period": "P1D"}
        config.data=input_tf
        config.method = "sum"
        config.argument ={"threshold": 3}

        dataset_repository = {"ts_1": container}

        pipeline = AggregationPipeline()

        result = pipeline.apply(config=config, dataset_repository=dataset_repository)
        assert_frame_equal(result.df, expected_df)
