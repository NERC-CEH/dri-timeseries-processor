from datetime import datetime

import polars as pl
from polars.testing import assert_series_equal

from dritimeseriesprocessor.models.domain_models.processing_config import DataProcessingMethodConfig
from dritimeseriesprocessor.operations.quality_control.qc_methods import (
    BatteryVoltage,
    ErrorCode,
    HeatFluxPlateRemoval,
    Nr01Temp,
    PluvioDiagnostic,
    Range,
    Samples,
    SnowDaySignal,
    Spike,
    TdtTSoil,
)
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


class TestRange:
    def test_range_simple(self) -> None:
        """Test that the range function works across the full DataFrame."""
        tf = create_timeframe([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0])
        config = create_method_config(lt=3, gt=5)

        result = Range().run(tf, config)

        expected = pl.Series([True, True, False, False, False, True, True])
        assert_series_equal(result, expected)

    def test_range_with_date_filter(self) -> None:
        """Test that the range function works with a date filter."""
        tf = create_timeframe([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0])
        config = create_method_config(
            lt=3,
            gt=5,
            start_date=datetime(2025, 1, 1, 2),
            end_date=datetime(2025, 1, 1, 4, 59),
        )

        result = Range().run(tf, config)

        expected = pl.Series([False, False, False, False, False, False, False])
        assert_series_equal(result, expected)


class TestBatteryVoltage:
    def test_battv_simple(self) -> None:
        """Test that the BatteryVoltage function works across the full DataFrame."""
        tf = create_timeframe([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0])
        config = create_method_config(lt=4)

        result = BatteryVoltage().run(tf, config)

        expected = pl.Series([True, True, True, False, False, False, False])
        assert_series_equal(result, expected)

    def test_battv_with_date_filter(self) -> None:
        """Test that the BatteryVoltage function works with a date filter."""
        tf = create_timeframe([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0])
        config = create_method_config(
            lt=4,
            start_date=datetime(2025, 1, 1, 2),
            end_date=datetime(2025, 1, 1, 4, 59),
        )

        result = BatteryVoltage().run(tf, config)

        expected = pl.Series([False, False, True, False, False, False, False])
        assert_series_equal(result, expected)


class TestSamples:
    def test_samples_simple(self) -> None:
        """Test that the samples function works across the full DataFrame."""
        tf = create_timeframe([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0])
        config = create_method_config(lt=4)

        result = Samples().run(tf, config)

        expected = pl.Series([True, True, True, False, False, False, False])
        assert_series_equal(result, expected)

    def test_samples_with_date_filter(self) -> None:
        """Test that the samples function works with a date filter."""
        tf = create_timeframe([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0])
        config = create_method_config(
            lt=4,
            start_date=datetime(2025, 1, 1, 2),
            end_date=datetime(2025, 1, 1, 4, 59),
        )

        result = Samples().run(tf, config)

        expected = pl.Series([False, False, True, False, False, False, False])
        assert_series_equal(result, expected)


class TestErrorCode:
    def test_error_code_simple(self) -> None:
        """Test that the error code function works across the full DataFrame."""
        tf = create_timeframe([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0])
        config = create_method_config(value=[5.0, 6.0, 7.0])

        result = ErrorCode().run(tf, config)

        expected = pl.Series([False, False, False, False, True, True, True])
        assert_series_equal(result, expected)

    def test_error_code_with_date_filter(self) -> None:
        """Test that the error code function works with a date filter."""
        tf = create_timeframe([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0])
        config = create_method_config(
            value=[5.0, 6.0, 7.0],
            start_date=datetime(2025, 1, 1, 2),
            end_date=datetime(2025, 1, 1, 4, 59),
        )

        result = ErrorCode().run(tf, config)

        expected = pl.Series([False, False, False, False, True, False, False])
        assert_series_equal(result, expected)


class TestSpike:
    def test_spike_simple(self) -> None:
        """Test that the spike function works across the full DataFrame."""
        tf = create_timeframe([1.0, 2.0, 30.0, 4.0, 5.0, 60.0, 7.0])
        config = create_method_config(gt=5.0)

        result = Spike().run(tf, config)

        expected = pl.Series([None, False, True, False, False, True, None])
        assert_series_equal(result, expected)

    def test_spike_with_date_filter(self) -> None:
        """Test that the spike function works with a date filter."""
        tf = create_timeframe([1.0, 2.0, 30.0, 4.0, 5.0, 60.0, 7.0])
        config = create_method_config(
            gt=5.0,
            start_date=datetime(2025, 1, 1, 2),
            end_date=datetime(2025, 1, 1, 4, 59),
        )

        result = Spike().run(tf, config)

        expected = pl.Series([False, False, True, False, False, False, False])
        assert_series_equal(result, expected)


class TestNr01Temp:
    def test_nr01_simple(self) -> None:
        """Test that the nr01 function works across the full DataFrame."""
        tf = create_timeframe([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0])
        config = create_method_config(lt=3, gt=5)

        result = Nr01Temp().run(tf, config)

        expected = pl.Series([True, True, False, False, False, True, True])
        assert_series_equal(result, expected)

    def test_nr01_with_date_filter(self) -> None:
        """Test that the nr01 function works with a date filter."""
        tf = create_timeframe([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0])
        config = create_method_config(
            lt=3,
            gt=5,
            start_date=datetime(2025, 1, 1, 2),
            end_date=datetime(2025, 1, 1, 4, 59),
        )

        result = Nr01Temp().run(tf, config)

        expected = pl.Series([False, False, False, False, False, False, False])
        assert_series_equal(result, expected)


class TestHeatFluxPlateRemoval:
    def test_hfp_simple(self) -> None:
        """Test that the hfp removal function works across the full DataFrame."""
        tf = create_timeframe([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0])
        config = create_method_config(time_ge="01:00:00", time_le="03:00:00")

        result = HeatFluxPlateRemoval().run(tf, config)

        expected = pl.Series([False, True, True, True, False, False, False])
        assert_series_equal(result, expected)

    def test_hfp_with_date_filter(self) -> None:
        """Test that the hfp removal function works with a date filter."""
        tf = create_timeframe([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0])
        config = create_method_config(
            time_ge="01:00:00",
            time_le="03:00:00",
            start_date=datetime(2025, 1, 1, 2),
            end_date=datetime(2025, 1, 1, 4, 59),
        )

        result = HeatFluxPlateRemoval().run(tf, config)

        expected = pl.Series([False, False, True, True, False, False, False])
        assert_series_equal(result, expected)


class TestPluvioDiagnostic:
    def test_pluvio_diagnostic_simple(self) -> None:
        """Test that the pluvio_diagnostic function works across the full DataFrame."""
        tf = create_timeframe([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0])
        config = create_method_config(gt=4)

        result = PluvioDiagnostic().run(tf, config)

        expected = pl.Series([False, False, False, False, True, True, True])
        assert_series_equal(result, expected)

    def test_pluvio_diagnostic_with_date_filter(self) -> None:
        """Test that the pluvio_diagnostic function works with a date filter."""
        tf = create_timeframe([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0])
        config = create_method_config(
            gt=4,
            start_date=datetime(2025, 1, 1, 2),
            end_date=datetime(2025, 1, 1, 4, 59),
        )

        result = PluvioDiagnostic().run(tf, config)

        expected = pl.Series([False, False, False, False, True, False, False])
        assert_series_equal(result, expected)


class TestSnowDaySignal:
    def test_snowday_simple(self) -> None:
        """Test that the snowday function works across the full DataFrame."""
        tf = create_timeframe([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0])
        config = create_method_config(lt=4)

        result = SnowDaySignal().run(tf, config)

        expected = pl.Series([True, True, True, False, False, False, False])
        assert_series_equal(result, expected)

    def test_snowday_with_date_filter(self) -> None:
        """Test that the snowday function works with a date filter."""
        tf = create_timeframe([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0])
        config = create_method_config(
            lt=4,
            start_date=datetime(2025, 1, 1, 2),
            end_date=datetime(2025, 1, 1, 4, 59),
        )

        result = SnowDaySignal().run(tf, config)

        expected = pl.Series([False, False, True, False, False, False, False])
        assert_series_equal(result, expected)


class TestTdtTSoil:
    def test_tdt_soil_simple(self) -> None:
        """Test that the tdt_soil function works across the full DataFrame."""
        tf = create_timeframe([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0])
        config = create_method_config(lt=4)

        result = TdtTSoil().run(tf, config)

        expected = pl.Series([True, True, True, False, False, False, False])
        assert_series_equal(result, expected)

    def test_tdt_soil_with_date_filter(self) -> None:
        """Test that the tdt_soil function works with a date filter."""
        tf = create_timeframe([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0])
        config = create_method_config(
            lt=4,
            start_date=datetime(2025, 1, 1, 2),
            end_date=datetime(2025, 1, 1, 4, 59),
        )

        result = TdtTSoil().run(tf, config)

        expected = pl.Series([False, False, True, False, False, False, False])
        assert_series_equal(result, expected)
