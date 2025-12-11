from datetime import datetime
from unittest.mock import MagicMock

import polars as pl
import time_stream as ts
from polars.testing import assert_frame_equal

from new_processor.models.domain_models.processing_config import MethodConfig
from new_processor.operations.aggregation.aggregation_pipeline import AggregationPipeline


def create_mock_timeframe(col_name: str) -> ts.TimeFrame:
    """Create a mock TimeFrame with necessary attributes."""
    time_vals = [datetime(2025, 1, 1), datetime(2025, 1, 2), datetime(2025, 1, 3)]
    metadata = {"column_name": col_name}
    df = pl.DataFrame({"time": time_vals, col_name: [4, 5, 6]})
    tf = ts.TimeFrame(df, "time").with_metadata(metadata)
    return tf


class TestCreateAggregationMethodConfig:
    def test_create_method_config(self) -> None:
        """Test that method config can be created from given container."""
        pipeline = AggregationPipeline()

        container = MagicMock()
        container.periodicity = "PT1H"
        container.method = "http://example.com/id/method_id"

        result = pipeline._create_aggregation_method_config(container)

        expected = MethodConfig(
            method="method_id",
            params={"aggregation_period": ts.Period.of_hours(1)},
        )

        assert result == expected


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
