from datetime import datetime

import polars as pl
import time_stream as ts
from polars.testing import assert_frame_equal

from dritimeseriesprocessor.models.domain_models.processing_config import ProcessingMethodConfig
from dritimeseriesprocessor.operations.aggregation.aggregation_methods import Max, Mean, Min, Sum
from utils.data_creation import create_timeframe


def create_method_config(periodicity: ts.Period) -> ProcessingMethodConfig:
    """Create a test MethodConfig.

    Args:
        periodicity: Aggregation periodicity

    Returns:
        MethodConfig for testing
    """
    return ProcessingMethodConfig(
        method="test",
        params={"aggregation_period": periodicity},
    )


class TestMin:
    def test_min(self) -> None:
        """Test that the min aggregation works across the full DataFrame."""
        tf = create_timeframe(list(range(24)))
        config = create_method_config(ts.Period.of_days(1))

        result = Min().run(tf, config)
        expected = pl.DataFrame({"time": [datetime(2025, 1, 1)], "value": [0]})
        assert_frame_equal(result.df, expected)


class TestMax:
    def test_max(self) -> None:
        """Test that the max aggregation works across the full DataFrame."""
        tf = create_timeframe(list(range(24)))
        config = create_method_config(ts.Period.of_days(1))

        result = Max().run(tf, config)
        expected = pl.DataFrame({"time": [datetime(2025, 1, 1)], "value": [23]})
        assert_frame_equal(result.df, expected)


class TestMean:
    def test_mean(self) -> None:
        """Test that the mean aggregation works across the full DataFrame."""
        tf = create_timeframe(list(range(24)))
        config = create_method_config(ts.Period.of_days(1))

        result = Mean().run(tf, config)
        expected = pl.DataFrame({"time": [datetime(2025, 1, 1)], "value": [11.5]})
        assert_frame_equal(result.df, expected)


class TestSum:
    def test_sum(self) -> None:
        """Test that the sum aggregation works across the full DataFrame."""
        tf = create_timeframe(list(range(24)))
        config = create_method_config(ts.Period.of_days(1))

        result = Sum().run(tf, config)
        expected = pl.DataFrame({"time": [datetime(2025, 1, 1)], "value": [276]})
        assert_frame_equal(result.df, expected)
