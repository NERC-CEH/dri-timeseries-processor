from datetime import datetime

import polars as pl
import pytest
import time_stream as ts
from polars.testing import assert_frame_equal

from dritimeseriesprocessor.models.domain_models.processing_config import DataProcessingMethodConfig
from dritimeseriesprocessor.operations.aggregation.aggregation_methods import (
<<<<<<< HEAD
<<<<<<< HEAD
    AggregationMethod,
=======
>>>>>>> dcc62bc (Add StandardDeviation method to aggregation methods. Add unit test. ToDo: Test unit test and pipeline with new metadata)
=======
>>>>>>> 81524a3 (Add StandardDeviation method to aggregation methods. Add unit test. ToDo: Test unit test and pipeline with new metadata)
    AngularMean,
    Max,
    Mean,
    MeanRad,
    Min,
<<<<<<< HEAD
<<<<<<< HEAD
=======
    StandardDeviation,
>>>>>>> dcc62bc (Add StandardDeviation method to aggregation methods. Add unit test. ToDo: Test unit test and pipeline with new metadata)
=======
    StandardDeviation,
>>>>>>> 81524a3 (Add StandardDeviation method to aggregation methods. Add unit test. ToDo: Test unit test and pipeline with new metadata)
    Sum,
)
from utils.data_creation import create_timeframe

AGG_TESTS = [
    pytest.param(Min, {"full_day": 0, "time_window": 11, "window_outside_data": None}, id="min"),
    pytest.param(Max, {"full_day": 23, "time_window": 14, "window_outside_data": None}, id="max"),
    pytest.param(Mean, {"full_day": 11.5, "time_window": 12.5, "window_outside_data": None}, id="mean"),
    pytest.param(Sum, {"full_day": 276, "time_window": 50, "window_outside_data": None}, id="sum"),
    pytest.param(AngularMean, {"full_day": 59.5, "time_window": 60.5, "window_outside_data": None}, id="angular_mean"),
    pytest.param(MeanRad, {"full_day": 0.9936, "time_window": 1.08, "window_outside_data": None}, id="mean_rad"),
]


def create_method_config(periodicity: ts.Period) -> DataProcessingMethodConfig:
    """Create a test MethodConfig.

    Args:
        periodicity: Aggregation periodicity

    Returns:
        MethodConfig for testing
    """
    return DataProcessingMethodConfig(
        method="test",
        params={"aggregation_period": periodicity, "threshold": 43},
    )


@pytest.mark.parametrize("agg_cls,expected", AGG_TESTS)
@pytest.mark.parametrize("mode", ["full_day", "time_window", "window_outside_data"])
def test_aggregation_methods(
    mode: str, agg_cls: type[AggregationMethod], expected: dict[str, int | float | None]
) -> None:
    expected_value = expected[mode]

    if agg_cls is AngularMean:
        if mode != "window_outside_data":
            tf = create_timeframe(list(range(24 * 2, 24 * 3, 1)))
        else:
            tf = create_timeframe(list(range(24 * 2, 24 * 2 + 12, 1)))
    else:
        if mode != "window_outside_data":
            tf = create_timeframe(list(range(24)))
        else:
            tf = create_timeframe(list(range(12)))

    if mode != "window_outside_data":
        expected_df = pl.DataFrame(
            {
                "time": [datetime(2025, 1, 1)],
                "value": [expected_value],
            }
        )

    config = create_method_config(ts.Period.of_days(1))
    if mode == "time_window":
        config.params["start_time"] = "10:30:00"
        config.params["end_time"] = "14:00:00"
        config.argument = {"threshold": 7}

    elif mode == "window_outside_data":
        config.params["start_time"] = "20:00:00"
        config.params["end_time"] = "23:00:00"

    result = agg_cls().run(tf, config)

    if mode != "window_outside_data":
        assert_frame_equal(result.df["time", "value"], expected_df)
    else:
        assert result.df.is_empty()


class TestSum:
    def test_sum(self) -> None:
        """Test that the sum aggregation works across the full DataFrame."""
        tf = create_timeframe(list(range(24)))
        config = create_method_config(ts.Period.of_days(1))

        result = Sum().run(tf, config)
        expected = pl.DataFrame({"time": [datetime(2025, 1, 1)], "value": [276]})
        assert_frame_equal(result.df["time", "value"], expected)


class TestAngularMean:
    def test_angular_mean(self) -> None:
        """Test that the angular mean, e.g. daily wind direction, aggregation works across the full DataFrame."""
        tf = create_timeframe(list(range(24 * 3)))
        config = create_method_config(ts.Period.of_days(1))

        result = AngularMean().run(tf, config)
        expected = pl.DataFrame(
            {"time": [datetime(2025, 1, 1), datetime(2025, 1, 2), datetime(2025, 1, 3)], "value": [11.5, 35.5, 59.5]}
        )
        assert_frame_equal(result.df["time", "value"], expected)


class TestMeanRad:
    def test_mean_rad(self) -> None:
        """Test that the daily radiation aggregation works across the full dataframe"""
        tf = create_timeframe(list(range(24)))
        config = create_method_config(ts.Period.of_days(1))

        result = MeanRad().run(tf, config)
        expected = pl.DataFrame({"time": [datetime(2025, 1, 1)], "value": [0.9936]})
        assert_frame_equal(result.df["time", "value"], expected)


class TestThresholdArgument:
    @pytest.mark.parametrize("threshold", [1, 24, 42])
    def test_threshold(self, threshold: int) -> None:
        """Check aggregation for different threshold values"""
        tf = create_timeframe(list(range(24)))
        config = create_method_config(ts.Period.of_days(1))
        config.argument = {"threshold": threshold}

        result = Sum().run(tf, config)
        expected = pl.DataFrame({"time": [datetime(2025, 1, 1)], "value": [276]})
        assert_frame_equal(result.df["time", "value"], expected["time", "value"])


class TestStandardDeviation:
    def test_standard_deviation(self) -> None:
        """Test that the sum aggregation works across the full DataFrame."""
        tf = create_timeframe(list(range(24)))
        config = create_method_config(ts.Period.of_days(1))
        config.params["start_time"] = "10:30:00"
        config.params["end_time"] = "14:00:00"
        config.argument = {"threshold": 7}

        result = StandardDeviation().run(tf, config)
        expected = pl.DataFrame({"time": [datetime(2025, 1, 1)], "value": [1.290994]})
        assert_frame_equal(result.df["time", "value"], expected)

    def test_standard_deviation_below_threshold(self) -> None:
        """Test that the sum aggregation works across the full DataFrame."""
        tf = create_timeframe(list(range(9, 13)))
        config = create_method_config(ts.Period.of_days(1))
        config.params["start_time"] = "10:30:00"
        config.params["end_time"] = "14:00:00"
        config.argument = {"threshold": 7}

        result = StandardDeviation().run(tf, config)
        expected = pl.DataFrame(
            schema={
                "time": pl.Datetime("us"),
                "value": pl.Float64,
            }
        )
        assert_frame_equal(result.df["time", "value"], expected)
>>>>>>> 81524a3 (Add StandardDeviation method to aggregation methods. Add unit test. ToDo: Test unit test and pipeline with new metadata)
