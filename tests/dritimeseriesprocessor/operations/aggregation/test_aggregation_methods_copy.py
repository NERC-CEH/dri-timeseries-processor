from datetime import datetime

import polars as pl
import pytest
import time_stream as ts
from polars.testing import assert_frame_equal

from dritimeseriesprocessor.models.domain_models.processing_config import DataProcessingMethodConfig
from dritimeseriesprocessor.operations.aggregation.aggregation_methods import (
    AggregationMethod,
    AngularMean,
    Max,
    Mean,
    MeanRad,
    Min,
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

    elif mode == "window_outside_data":
        config.params["start_time"] = "20:00:00"
        config.params["end_time"] = "23:00:00"

    result = agg_cls().run(tf, config)

    if mode != "window_outside_data":
        assert_frame_equal(result.df["time", "value"], expected_df)
    else:
        assert result.df.is_empty()
