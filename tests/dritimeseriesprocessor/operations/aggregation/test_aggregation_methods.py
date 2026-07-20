from datetime import datetime

import polars as pl
import pytest
import time_stream as ts
from polars.testing import assert_frame_equal

from dritimeseriesprocessor.models.domain_models.processing_config import DataProcessingMethodConfig
from dritimeseriesprocessor.operations.aggregation.aggregation_methods import (
    AngularMean,
    Max,
    Mean,
    MeanRad,
    Min,
    RollingMeanForCounts,
    StandardDeviation,
    Sum,
)
from utils.data_creation import create_timeframe


def create_aggregation_config(periodicity: ts.Period) -> DataProcessingMethodConfig:
    """Create a test MethodConfig.

    Args:
        periodicity: Aggregation periodicity

    Returns:
        MethodConfig for testing
    """
    return DataProcessingMethodConfig(
        method="test",
        params={"aggregation_period": periodicity, "aggregation_time_anchor": "start", "threshold": 43},
    )


def create_rolling_aggregation_config() -> DataProcessingMethodConfig:
    """Create a test MethodConfig.

    Args:
        None

    Returns:
        MethodConfig for testing
    """
    return DataProcessingMethodConfig(
        method="test",
    )


class TestMin:
    def test_min(self) -> None:
        """Test that the min aggregation works across the full DataFrame."""
        tf = create_timeframe(list(range(24)))
        config = create_aggregation_config(ts.Period.of_days(1))

        result = Min().run(tf, config)
        expected = pl.DataFrame({"time": [datetime(2025, 1, 1)], "value": [0]})
        assert_frame_equal(result.df["time", "value"], expected)


class TestMax:
    def test_max(self) -> None:
        """Test that the max aggregation works across the full DataFrame."""
        tf = create_timeframe(list(range(24)))
        config = create_aggregation_config(ts.Period.of_days(1))

        result = Max().run(tf, config)
        expected = pl.DataFrame({"time": [datetime(2025, 1, 1)], "value": [23]})
        assert_frame_equal(result.df["time", "value"], expected)


class TestMean:
    def test_mean(self) -> None:
        """Test that the mean aggregation works across the full DataFrame."""
        tf = create_timeframe(list(range(24)))
        config = create_aggregation_config(ts.Period.of_days(1))

        result = Mean().run(tf, config)
        expected = pl.DataFrame({"time": [datetime(2025, 1, 1)], "value": [11.5]})
        assert_frame_equal(result.df["time", "value"], expected)

    def test_mean_with_time_window(self) -> None:
        """Test that the mean aggregation works when a time window is specified."""
        tf = create_timeframe(list(range(24)))
        config = create_aggregation_config(ts.Period.of_days(1))
        config.params["start_time"] = "10:30:00"
        config.params["end_time"] = "14:00:00"

        result = Mean().run(tf, config)
        expected = pl.DataFrame({"time": [datetime(2025, 1, 1)], "value": [12.5]})
        assert_frame_equal(result.df["time", "value"], expected)


class TestSum:
    def test_sum(self) -> None:
        """Test that the sum aggregation works across the full DataFrame."""
        tf = create_timeframe(list(range(24)))
        config = create_aggregation_config(ts.Period.of_days(1))

        result = Sum().run(tf, config)
        expected = pl.DataFrame({"time": [datetime(2025, 1, 1)], "value": [276]})
        assert_frame_equal(result.df["time", "value"], expected)


class TestAngularMean:
    def test_angular_mean(self) -> None:
        """Test that the angular mean, e.g. daily wind direction, aggregation works across the full DataFrame."""
        tf = create_timeframe(list(range(24 * 3)))
        config = create_aggregation_config(ts.Period.of_days(1))

        result = AngularMean().run(tf, config)
        expected = pl.DataFrame(
            {"time": [datetime(2025, 1, 1), datetime(2025, 1, 2), datetime(2025, 1, 3)], "value": [11.5, 35.5, 59.5]}
        )
        assert_frame_equal(result.df["time", "value"], expected)


class TestMeanRad:
    def test_mean_rad(self) -> None:
        """Test that the daily radiation aggregation works across the full dataframe"""
        tf = create_timeframe(list(range(24)))
        config = create_aggregation_config(ts.Period.of_days(1))

        result = MeanRad().run(tf, config)
        expected = pl.DataFrame({"time": [datetime(2025, 1, 1)], "value": [0.9936]})
        assert_frame_equal(result.df["time", "value"], expected)


class TestThresholdArgument:
    @pytest.mark.parametrize("threshold", [1, 24, 42])
    def test_threshold(self, threshold: int) -> None:
        """Check aggregation for different threshold values"""
        tf = create_timeframe(list(range(24)))
        config = create_aggregation_config(ts.Period.of_days(1))
        config.params["threshold"] = threshold

        result = Sum().run(tf, config)
        expected = pl.DataFrame({"time": [datetime(2025, 1, 1)], "value": [276]})
        assert_frame_equal(result.df["time", "value"], expected["time", "value"])


class TestStandardDeviation:
    def test_standard_deviation(self) -> None:
        """Test that the sum aggregation works across the full DataFrame."""
        tf = create_timeframe(list(range(24)))
        config = create_aggregation_config(ts.Period.of_days(1))
        config.params["start_time"] = "10:30:00"
        config.params["end_time"] = "14:00:00"
        config.params["threshold"] = 7

        result = StandardDeviation().run(tf, config)
        expected = pl.DataFrame({"time": [datetime(2025, 1, 1)], "value": [1.290994]})
        assert_frame_equal(result.df["time", "value"], expected)

    def test_standard_deviation_below_threshold(self) -> None:
        """Test that the sum aggregation works across the full DataFrame."""
        tf = create_timeframe(list(range(9, 13)))
        config = create_aggregation_config(ts.Period.of_days(1))
        config.params["start_time"] = "10:30:00"
        config.params["end_time"] = "14:00:00"
        config.params["threshold"] = 7

        result = StandardDeviation().run(tf, config)
        expected = pl.DataFrame(
            schema={
                "time": pl.Datetime("us"),
                "value": pl.Float64,
            }
        )
        assert_frame_equal(result.df["time", "value"], expected)


class TestRollingMeanForCounts:
    def test_rolling_mean_for_counts(self) -> None:
        """
        Windows with less than the threshold amount of non nulls produce null output.

        Datapoints that have window // 2 datapoints on either side,
        and have at least the threshold number of non null values in their window
        have a rolling mean applied.

        Datapoints at the edges of the dataset that do not have a complete window,
        are assigned a null value for the mean.
        """
        tf = create_timeframe(
            column_name="value",
            values=[
                100.0,
                101.0,
                102.0,
                None,
                None,
                None,
                103.0,
                104.0,
                105.0,
                None,
                None,
                106.0,
                107.0,
                108.0,
                109.0,
            ],
        )
        config = create_rolling_aggregation_config()
        config.params["window_size"] = "PT5H"
        config.params["threshold"] = 3
        config.params["alignment"] = "center"

        expected = pl.DataFrame(
            {
                "value": pl.Series(
                    [
                        None,
                        None,
                        101.0,
                        None,
                        None,
                        None,
                        104.0,
                        104.0,
                        104.0,
                        105.0,
                        106.0,
                        107.0,
                        107.5,
                        None,
                        None,
                    ],
                    dtype=pl.Float64,
                )
            }
        )
        result = RollingMeanForCounts().run(tf, config)
        assert_frame_equal(result.df.select("value"), expected)

    def test_rolling_mean_trailing_alignment(self) -> None:
        """With trailing alignment, each window ends at the current point, so only the start of the
        dataset is masked, not the end."""
        tf = create_timeframe(
            column_name="value",
            values=[
                100.0,
                101.0,
                102.0,
                None,
                None,
                None,
                103.0,
                104.0,
                105.0,
                None,
                None,
                106.0,
                107.0,
                108.0,
                109.0,
            ],
        )
        config = create_rolling_aggregation_config()
        config.params["window_size"] = "PT5H"
        config.params["threshold"] = 3
        config.params["alignment"] = "trailing"

        expected = pl.DataFrame(
            {
                "value": pl.Series(
                    [
                        None,
                        None,
                        None,
                        None,
                        101.0,
                        None,
                        None,
                        None,
                        104.0,
                        104.0,
                        104.0,
                        105.0,
                        106.0,
                        107.0,
                        107.5,
                    ],
                    dtype=pl.Float64,
                )
            }
        )
        result = RollingMeanForCounts().run(tf, config)
        assert_frame_equal(result.df.select("value"), expected)

    def test_rolling_mean_leading_alignment(self) -> None:
        """With leading alignment, each window starts at the current point, so only the end of the
        dataset is masked, not the start."""
        tf = create_timeframe(
            column_name="value",
            values=[
                100.0,
                101.0,
                102.0,
                None,
                None,
                None,
                103.0,
                104.0,
                105.0,
                None,
                None,
                106.0,
                107.0,
                108.0,
                109.0,
            ],
        )
        config = create_rolling_aggregation_config()
        config.params["window_size"] = "PT5H"
        config.params["threshold"] = 3
        config.params["alignment"] = "leading"

        expected = pl.DataFrame(
            {
                "value": pl.Series(
                    [
                        101.0,
                        None,
                        None,
                        None,
                        104.0,
                        104.0,
                        104.0,
                        105.0,
                        106.0,
                        107.0,
                        107.5,
                        None,
                        None,
                        None,
                        None,
                    ],
                    dtype=pl.Float64,
                )
            }
        )
        result = RollingMeanForCounts().run(tf, config)
        assert_frame_equal(result.df.select("value"), expected)
