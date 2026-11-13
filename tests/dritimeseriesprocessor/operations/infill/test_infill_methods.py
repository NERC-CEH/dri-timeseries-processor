from datetime import datetime

import polars as pl
import pytest
from polars.testing import assert_frame_equal

from dritimeseriesprocessor.models.domain_models.processing_config import DataProcessingMethodConfig
from dritimeseriesprocessor.operations.infill.infill_methods import AltData, AltDataDynamic, Linear, ZeroFill
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
        alt_data_source = create_timeframe([10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0], "alt")
        config = create_method_config(
            alt_data_source=alt_data_source,
        )

        result = AltData().run(tf, config)

        expected = [1.0, 20.0, 3.0, 40.0, 5.0, 60.0, 7.0]
        expected_df = pl.DataFrame({"time": [datetime(2025, 1, 1, h) for h in range(7)], "value": expected})

        assert_frame_equal(result.df, expected_df)

    def test_alt_data_with_date_filter(self) -> None:
        """Test that the alt_data function works with a date filter."""
        tf = create_timeframe([1.0, None, 3.0, None, 5.0, None, 7.0])
        alt_data_source = create_timeframe([10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0], "alt")
        config = create_method_config(
            alt_data_source=alt_data_source,
            start_date=datetime(2025, 1, 1, 2),
            end_date=datetime(2025, 1, 1, 4, 59),
        )

        result = AltData().run(tf, config)

        expected = [1.0, None, 3.0, 40.0, 5.0, None, 7.0]
        expected_df = pl.DataFrame({"time": [datetime(2025, 1, 1, h) for h in range(7)], "value": expected})

        assert_frame_equal(result.df, expected_df)

    def test_alt_data_source_sharing_column_name_with_tf(self) -> None:
        """Tests that an alternative dataset with the same column name as the data being infilled is used to fill it."""
        tf = create_timeframe([1.0, None, 3.0, None, 5.0, None, 7.0])
        alt_data_source = create_timeframe([10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0])
        config = create_method_config(alt_data_source=alt_data_source)

        result = AltData().run(tf, config)

        expected = [1.0, 20.0, 3.0, 40.0, 5.0, 60.0, 7.0]
        expected_df = pl.DataFrame({"time": [datetime(2025, 1, 1, h) for h in range(7)], "value": expected})

        assert_frame_equal(result.df, expected_df)


class TestAltDataDynamic:
    def test_alt_data_simple(self) -> None:
        """Test that the alt_data_dynamic function works across the full DataFrame."""
        tf = create_timeframe([1.0, None, 3.0, None, 5.0, None, 7.0])
        alt_data_source = create_timeframe([10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0], "alt")
        config = create_method_config(
            alt_data_source=alt_data_source,
            max_threshold=2,
            window="PT1H",
        )

        result = AltDataDynamic().run(tf, config)

        expected = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0]
        expected_df = pl.DataFrame({"time": [datetime(2025, 1, 1, h) for h in range(7)], "value": expected})

        assert_frame_equal(result.df, expected_df)

    def test_alt_data_with_date_filter(self) -> None:
        """Test that the alt_data function works with a date filter."""
        tf = create_timeframe([1.0, None, 3.0, None, 5.0, None, 7.0])
        alt_data_source = create_timeframe([10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0], "alt")
        config = create_method_config(
            alt_data_source=alt_data_source,
            start_date=datetime(2025, 1, 1, 2),
            end_date=datetime(2025, 1, 1, 4, 59),
            min_threshold=2,
            max_threshold=2,
            window="PT1H",
        )

        result = AltDataDynamic().run(tf, config)

        expected = [1.0, None, 3.0, 4.0, 5.0, None, 7.0]
        expected_df = pl.DataFrame({"time": [datetime(2025, 1, 1, h) for h in range(7)], "value": expected})

        assert_frame_equal(result.df, expected_df)

    def test_alt_data_missing_window_raises(self) -> None:
        """Test that the alt_data_dynamic function raises a KeyError when window is not given in config."""
        tf = create_timeframe([1.0, None, 3.0, None, 5.0, None, 7.0])
        alt_data_source = create_timeframe([10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0], "alt")
        config = create_method_config(
            alt_data_source=alt_data_source,
        )

        with pytest.raises(KeyError):
            AltDataDynamic().run(tf, config)


class TestZeroFill:
    @staticmethod
    def expected_df(values: list[float | None]) -> pl.DataFrame:
        return pl.DataFrame({"time": [datetime(2025, 1, 1, h) for h in range(len(values))], "value": values})

    def test_zero_fill_simple(self) -> None:
        """Test that null values are filled with 0 and present values are unchanged."""
        tf = create_timeframe([None, 2.0, None, 4.0, None, 6.0, None])

        result = ZeroFill().run(tf, create_method_config())

        assert_frame_equal(result.df, self.expected_df([0.0, 2.0, 0.0, 4.0, 0.0, 6.0, 0.0]))

    def test_zero_fill_nan(self) -> None:
        """Test that NaN values are filled as well as null values."""
        tf = create_timeframe([float("nan"), 2.0, None, 4.0, float("nan"), 6.0, 7.0])

        result = ZeroFill().run(tf, create_method_config())

        assert_frame_equal(result.df, self.expected_df([0.0, 2.0, 0.0, 4.0, 0.0, 6.0, 7.0]))

    def test_zero_fill_with_date_filter(self) -> None:
        """Test that only missing values within the date range are filled, inclusive at both ends."""
        tf = create_timeframe([None, None, None, None, None, None, 7.0])
        config = create_method_config(
            start_date=datetime(2025, 1, 1, 2),
            end_date=datetime(2025, 1, 1, 4),
        )

        result = ZeroFill().run(tf, config)

        assert_frame_equal(result.df, self.expected_df([None, None, 0.0, 0.0, 0.0, None, 7.0]))
