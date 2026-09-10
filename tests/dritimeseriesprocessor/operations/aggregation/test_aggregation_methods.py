from datetime import datetime, timedelta

import polars as pl
import pytest
import time_stream as ts
from isoperiod import Period
from polars.testing import assert_frame_equal

from dritimeseriesprocessor.models.domain_models.processing_config import DataProcessingMethodConfig
from dritimeseriesprocessor.operations.aggregation.aggregation_methods import (
    AngularMean,
    Max,
    Mean,
    MeanRad,
    Min,
    PointEstimate,
    RollingMeanForCounts,
    StandardDeviation,
    Sum,
)
from utils.data_creation import create_timeframe


def create_aggregation_config(periodicity: Period) -> DataProcessingMethodConfig:
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
        config = create_aggregation_config(Period.of_days(1))

        result = Min().run(tf, config)
        expected = pl.DataFrame({"time": [datetime(2025, 1, 1)], "value": [0]})
        assert_frame_equal(result.df["time", "value"], expected)


class TestMax:
    def test_max(self) -> None:
        """Test that the max aggregation works across the full DataFrame."""
        tf = create_timeframe(list(range(24)))
        config = create_aggregation_config(Period.of_days(1))

        result = Max().run(tf, config)
        expected = pl.DataFrame({"time": [datetime(2025, 1, 1)], "value": [23]})
        assert_frame_equal(result.df["time", "value"], expected)


class TestMean:
    def test_mean(self) -> None:
        """Test that the mean aggregation works across the full DataFrame."""
        tf = create_timeframe(list(range(24)))
        config = create_aggregation_config(Period.of_days(1))

        result = Mean().run(tf, config)
        expected = pl.DataFrame({"time": [datetime(2025, 1, 1)], "value": [11.5]})
        assert_frame_equal(result.df["time", "value"], expected)

    def test_mean_with_time_window(self) -> None:
        """Test that the mean aggregation works when a time window is specified."""
        tf = create_timeframe(list(range(24)))
        config = create_aggregation_config(Period.of_days(1))
        config.params["start_time"] = "10:30:00"
        config.params["end_time"] = "14:00:00"

        result = Mean().run(tf, config)
        expected = pl.DataFrame({"time": [datetime(2025, 1, 1)], "value": [12.5]})
        assert_frame_equal(result.df["time", "value"], expected)


class TestSum:
    def test_sum(self) -> None:
        """Test that the sum aggregation works across the full DataFrame."""
        tf = create_timeframe(list(range(24)))
        config = create_aggregation_config(Period.of_days(1))

        result = Sum().run(tf, config)
        expected = pl.DataFrame({"time": [datetime(2025, 1, 1)], "value": [276]})
        assert_frame_equal(result.df["time", "value"], expected)


class TestAngularMean:
    def test_angular_mean(self) -> None:
        """Test that the angular mean, e.g. daily wind direction, aggregation works across the full DataFrame."""
        tf = create_timeframe(list(range(24 * 3)))
        config = create_aggregation_config(Period.of_days(1))

        result = AngularMean().run(tf, config)
        expected = pl.DataFrame(
            {"time": [datetime(2025, 1, 1), datetime(2025, 1, 2), datetime(2025, 1, 3)], "value": [11.5, 35.5, 59.5]}
        )
        assert_frame_equal(result.df["time", "value"], expected)


class TestMeanRad:
    def test_mean_rad(self) -> None:
        """Test that the daily radiation aggregation works across the full dataframe"""
        tf = create_timeframe(list(range(24)))
        config = create_aggregation_config(Period.of_days(1))

        result = MeanRad().run(tf, config)
        expected = pl.DataFrame({"time": [datetime(2025, 1, 1)], "value": [0.9936]})
        assert_frame_equal(result.df["time", "value"], expected)


class TestThresholdArgument:
    @pytest.mark.parametrize("threshold", [1, 24, 42])
    def test_threshold(self, threshold: int) -> None:
        """Check aggregation for different threshold values"""
        tf = create_timeframe(list(range(24)))
        config = create_aggregation_config(Period.of_days(1))
        config.params["threshold"] = threshold

        result = Sum().run(tf, config)
        expected = pl.DataFrame({"time": [datetime(2025, 1, 1)], "value": [276]})
        assert_frame_equal(result.df["time", "value"], expected["time", "value"])


class TestStandardDeviation:
    def test_standard_deviation(self) -> None:
        """Test that the sum aggregation works across the full DataFrame."""
        tf = create_timeframe(list(range(24)))
        config = create_aggregation_config(Period.of_days(1))
        config.params["start_time"] = "10:30:00"
        config.params["end_time"] = "14:00:00"
        config.params["threshold"] = 7

        result = StandardDeviation().run(tf, config)
        expected = pl.DataFrame({"time": [datetime(2025, 1, 1)], "value": [1.290994]})
        assert_frame_equal(result.df["time", "value"], expected)

    def test_standard_deviation_below_threshold(self) -> None:
        """Test that the sum aggregation works across the full DataFrame."""
        tf = create_timeframe(list(range(9, 13)))
        config = create_aggregation_config(Period.of_days(1))
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


class TestPointEstimate:
    def test_point_estimate(self) -> None:
        """
        Test down sampling of hourly to daily data, for default "start-anchored" data.
        """
        tf = create_timeframe(list(range(48)))
        config = create_aggregation_config(Period.of_days(1))
        config.params["n"] = 12  # Use 12th hour of the day as the aggregation value

        result = PointEstimate().run(tf, config)
        expected = pl.DataFrame({"time": [datetime(2025, 1, 1), datetime(2025, 1, 2)], "value": [12, 36]})
        assert_frame_equal(result.df["time", "value"], expected)
        assert result.df["time_of_nth_value"].to_list() == [
            datetime(2025, 1, 1, 12),
            datetime(2025, 1, 2, 12),
        ]

    def test_point_estimate_with_end_time_anchor(self) -> None:
        """
        Test down sampling of hourly to daily data, for default "start-anchored" data.
        """
        dates = [datetime(2025, 1, 1) + timedelta(hours=h) for h in range(48)]
        df = pl.DataFrame({"time": dates, "value": list(range(48))})
        config = create_aggregation_config(Period.of_days(1))
        config.params["n"] = 12

        tf = ts.TimeFrame(df=df, time_name="time", resolution="PT1H", time_anchor="end").with_metadata(
            {"column_name": "value"}
        )

        result = PointEstimate().run(tf, config)
        assert result.df["value"].to_list()[1:] == [13, 37]
        assert result.df["time_of_nth_value"].to_list()[1:] == [
            datetime(2025, 1, 1, 13),
            datetime(2025, 1, 2, 13),
        ]


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

    def test_rolling_mean_month_based_window_raises(self) -> None:
        """Tests that a month-based window size raises a ValueError."""
        tf = create_timeframe([1.0, 2.0, 3.0])
        config = create_rolling_aggregation_config()
        config.params["window_size"] = "P1M"
        config.params["threshold"] = 1
        config.params["alignment"] = "center"

        with pytest.raises(ValueError):
            RollingMeanForCounts().run(tf, config)
