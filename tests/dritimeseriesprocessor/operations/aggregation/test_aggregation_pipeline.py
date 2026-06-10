from datetime import datetime
from unittest.mock import MagicMock

import polars as pl
import pytest
import time_stream as ts
from polars.testing import assert_frame_equal
from time_stream.period import Period

from dritimeseriesprocessor.models.domain_models.processing_config import DataProcessingMethodConfig
from dritimeseriesprocessor.operations.aggregation.aggregation_methods import Sum
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
                "value_CORE_FLAG": [2, 8, 8],  # estimated, removed, removed
            }
        )
        dep_container = MagicMock()
        dep_container.data = input_tf
        dep_container.source_column = "value"

        config = MagicMock()
        config.params = {
            "dep_ts": "ts_1",
            "aggregation_period": "P1D",
            "threshold": 3,
            "source_column": "value",
        }
        config.method = "sum"

        proc_config = MagicMock()
        proc_config.method_configs = [config]

        container = MagicMock()
        container.time_column_name = "time"
        container.source_column = "value"
        container.periodicity = "P1D"

        pipeline = AggregationPipeline()

        result = pipeline.run(container, {"ts_1": dep_container}, proc_config)
        assert_frame_equal(result.df, expected_df)


class TestRemoveData:
    @pytest.mark.parametrize(
        "valid,expected_value",
        [
            ([True, True, True], [1, 2, 3]),
            ([True, False, True], [1, None, 3]),
            ([False, False, False], [None, None, None]),
        ],
    )
    def test_remove_invalid(self, valid: list, expected_value: list) -> None:
        """Check rows marked as invalid are removed"""
        df = pl.DataFrame(
            {
                "time": [datetime(2025, 1, 1), datetime(2025, 1, 2), datetime(2025, 1, 3)],
                "value": [1, 2, 3],
                "valid_value": valid,
            }
        )
        input_tf = ts.TimeFrame(df, "time", resolution="P1D").with_metadata({"column_name": "value"})

        pipeline = AggregationPipeline()
        result = pipeline._remove_data(input_tf)
        expected = input_tf.with_df(df.with_columns(pl.Series("value", expected_value)))

        assert result == expected


class TestSelectColumns:
    def test_select_columns(self) -> None:
        """Check rows marked as invalid are removed"""
        df = pl.DataFrame(
            {
                "time": [datetime(2025, 1, 1, 0, 30), datetime(2025, 1, 1, 1), datetime(2025, 1, 1, 1, 30)],
                "value": [1, 2, 3],
            }
        )
        input_tf = ts.TimeFrame(df, "time", resolution="PT30M").with_metadata({"column_name": "value"})
        # Do an aggregation, which adds the additional metadata columns about expected values
        config = DataProcessingMethodConfig(method="test", params={"aggregation_period": "PT1H"})
        agg_tf = Sum().run(input_tf, config)

        pipeline = AggregationPipeline()
        result = pipeline._select_columns(agg_tf)

        expected_df = pl.DataFrame({"time": [datetime(2025, 1, 1), datetime(2025, 1, 1, 1)], "value": [1, 5]})
        expected_tf = ts.TimeFrame(expected_df, "time", resolution="PT1H").with_metadata({"column_name": "value"})

        assert result == expected_tf
