from datetime import datetime

import numpy as np
import polars as pl
import pytest
import time_stream as ts
from polars.testing import assert_frame_equal

from dritimeseriesprocessor.models.domain_models.processing_config import DataProcessingMethodConfig
from dritimeseriesprocessor.operations.aggregation.aggregation_methods import WD, Max, Mean, Min, Sum
from utils.data_creation import create_timeframe


def create_method_config(periodicity: ts.Period) -> DataProcessingMethodConfig:
    """Create a test MethodConfig.

    Args:
        periodicity: Aggregation periodicity

    Returns:
        MethodConfig for testing
    """
    return DataProcessingMethodConfig(
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


class TestWD:
    def test_angular_mean(self) -> None:
        """Test that the angular mean, e.g. daily wind direction, aggregation works across the full DataFrame."""
        tf = create_timeframe(list(range(24 * 3)))
        config = create_method_config(ts.Period.of_days(1))

        result = WD().run(tf, config)
        expected = pl.DataFrame(
            {"time": [datetime(2025, 1, 1), datetime(2025, 1, 2), datetime(2025, 1, 3)], "value": [11.5, 35.5, 59.5]}
        )
        assert_frame_equal(result.df.select(["time", "value"]), expected)


class TestRounding:
    def test_rounding_0(self) -> None:
        """Check a rounding value of 0 is applied correctly."""
        initial_values = np.arange(1, 2, 0.01)
        expected_values = np.around([26.76, 32.52, 38.28, 44.04, 7.9], 0)

        tf = create_timeframe(list(initial_values))
        config = create_method_config(ts.Period.of_days(1))
        config.argument = {"round": 0}

        result = Sum().run(tf, config)
        expected_df = pl.DataFrame(
            {
                "time": [
                    datetime(2025, 1, 1),
                    datetime(2025, 1, 2),
                    datetime(2025, 1, 3),
                    datetime(2025, 1, 4),
                    datetime(2025, 1, 5),
                ],
                "value": expected_values,
            }
        )
        assert_frame_equal(result.df, expected_df)

    def test_rounding_None(self) -> None:
        """Check no rounding is applied when no round argument is provided."""
        initial_values = np.arange(1, 2, 0.01)
        expected_values = [26.76, 32.52, 38.28, 44.04, 7.9]

        tf = create_timeframe(list(initial_values))
        config = create_method_config(ts.Period.of_days(1))
        config.argument = {}

        result = Sum().run(tf, config)
        expected_df = pl.DataFrame(
            {
                "time": [
                    datetime(2025, 1, 1),
                    datetime(2025, 1, 2),
                    datetime(2025, 1, 3),
                    datetime(2025, 1, 4),
                    datetime(2025, 1, 5),
                ],
                "value": expected_values,
            }
        )
        assert_frame_equal(result.df, expected_df)

    def test_rounding_invalid(self) -> None:
        """Check an error is raised when attempting to round with an invalid value such as -1."""
        initial_values = np.arange(1, 2, 0.01)

        tf = create_timeframe(list(initial_values))
        config = create_method_config(ts.Period.of_days(1))
        config.argument = {"round": -1}

        with pytest.raises(OverflowError, match="out of range integral type conversion attempted"):
            Sum().run(tf, config)
