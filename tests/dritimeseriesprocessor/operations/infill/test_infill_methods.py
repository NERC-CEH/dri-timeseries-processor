from datetime import datetime

import polars as pl
from polars.testing import assert_frame_equal

from dritimeseriesprocessor.models.domain_models.processing_config import DataProcessingMethodConfig
from dritimeseriesprocessor.operations.infill.infill_methods import AltData, Linear
from utils.data_creation import create_timeframe


def create_method_config(
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    **extra_params,
) -> DataProcessingMethodConfig:
    """Create a test MethodConfig.

    Args:
        start_date: Start date for the config
        end_date: End date for the config
        **extra_params: Additional parameters to add to config.params

    Returns:
        MethodConfig for testing
    """
    params = {}
    params.update(extra_params)

    return DataProcessingMethodConfig(
        method="test",
        params=params,
        start_date=start_date,
        end_date=end_date,
    )


class TestLinear:
    def test_linear_simple(self) -> None:
        """Test that the infill function works across the full DataFrame."""
        tf = create_timeframe([1.0, None, 3.0, None, 5.0, None, 7.0])
        config = create_method_config()

        result = Linear().run(tf, config)

        expected = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0]
        expected_df = pl.DataFrame({"time": [datetime(2025, 1, 1, h) for h in range(7)], "value": expected})

        assert_frame_equal(result.df, expected_df)

    def test_linear_with_date_filter(self) -> None:
        """Test that the infill function works with a date filter."""
        tf = create_timeframe([1.0, None, 3.0, None, 5.0, None, 7.0])
        config = create_method_config(
            start_date=datetime(2025, 1, 1, 2),
            end_date=datetime(2025, 1, 1, 4, 59),
        )

        result = Linear().run(tf, config)

        expected = [1.0, None, 3.0, 4.0, 5.0, None, 7.0]
        expected_df = pl.DataFrame({"time": [datetime(2025, 1, 1, h) for h in range(7)], "value": expected})

        assert_frame_equal(result.df, expected_df)


class TestAltData:
    def test_alt_data_simple(self) -> None:
        """Test that the alt_data function works across the full DataFrame."""
        tf = create_timeframe([1.0, None, 3.0, None, 5.0, None, 7.0])
        alt_df = pl.DataFrame(
            {"time": [datetime(2025, 1, 1, h) for h in range(7)], "alt": [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0]}
        )
        config = create_method_config(
            alt_df=alt_df,
            alt_data_column="alt",
        )

        result = AltData().run(tf, config)

        expected = [1.0, 20.0, 3.0, 40.0, 5.0, 60.0, 7.0]
        expected_df = pl.DataFrame({"time": [datetime(2025, 1, 1, h) for h in range(7)], "value": expected})

        assert_frame_equal(result.df, expected_df)

    def test_alt_data_with_date_filter(self) -> None:
        """Test that the alt_data function works with a date filter."""
        tf = create_timeframe([1.0, None, 3.0, None, 5.0, None, 7.0])
        alt_df = pl.DataFrame(
            {"time": [datetime(2025, 1, 1, h) for h in range(7)], "alt": [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0]}
        )
        config = create_method_config(
            alt_df=alt_df,
            alt_data_column="alt",
            start_date=datetime(2025, 1, 1, 2),
            end_date=datetime(2025, 1, 1, 4, 59),
        )

        result = AltData().run(tf, config)

        expected = [1.0, None, 3.0, 40.0, 5.0, None, 7.0]
        expected_df = pl.DataFrame({"time": [datetime(2025, 1, 1, h) for h in range(7)], "value": expected})

        assert_frame_equal(result.df, expected_df)
