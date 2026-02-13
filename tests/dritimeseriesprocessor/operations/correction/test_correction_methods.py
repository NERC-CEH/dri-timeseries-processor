from datetime import datetime

import polars as pl
import pytest
from polars.testing import assert_frame_equal

from dritimeseriesprocessor.models.domain_models.processing_config import DataProcessingMethodConfig
from dritimeseriesprocessor.operations.correction.correction_methods import (
    Add,
    Clip,
    CorrectionMethod,
    LWCorrection,
    PACorrection,
    Power,
    Scalar,
    WDCorrection,
)
from utils.data_creation import create_timeframe


def create_method_config(
    correction_factor: float | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    **extra_params,
) -> DataProcessingMethodConfig:
    """Create a test MethodConfig.

    Args:
        correction_factor: Correction factor value
        start_date: Start date for the config
        end_date: End date for the config
        **extra_params: Additional parameters to add to config.params

    Returns:
        MethodConfig for testing
    """
    params = {}
    if correction_factor is not None:
        params["correction_factor"] = correction_factor
    params.update(extra_params)

    return DataProcessingMethodConfig(
        method="test",
        params=params,
        start_date=start_date,
        end_date=end_date,
    )


def run_function_test(factor: float, expected: list[float], fn: CorrectionMethod) -> None:
    tf = create_timeframe()
    config = create_method_config(correction_factor=factor)
    result = fn.run(tf, config)
    expected_df = pl.DataFrame({"time": [datetime(2025, 1, 1, h) for h in range(7)], "value": expected})
    assert_frame_equal(result.df, expected_df)


def run_function_with_date_filter_test(factor: float, expected: list[float], fn: CorrectionMethod) -> None:
    tf = create_timeframe()
    config = create_method_config(
        correction_factor=factor,
        start_date=datetime(2025, 1, 1, 2),
        end_date=datetime(2025, 1, 1, 4, 59),
    )
    result = fn.run(tf, config)
    expected_df = pl.DataFrame({"time": [datetime(2025, 1, 1, h) for h in range(7)], "value": expected})
    assert_frame_equal(result.df, expected_df)


class TestAdd:
    @pytest.mark.parametrize(
        "factor,expected",
        [
            (100, [101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0]),
            (0, [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0]),
            (-1, [0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0]),
            (10.5, [11.5, 12.5, 13.5, 14.5, 15.5, 16.5, 17.5]),
        ],
    )
    def test_add_simple(self, factor: float, expected: list[float]) -> None:
        """Test that the add function works across the full DataFrame."""
        run_function_test(factor, expected, Add())

    def test_add_with_date_filter(self) -> None:
        """Test that the add function works with a date filter."""
        run_function_with_date_filter_test(10, [1.0, 2.0, 13.0, 14.0, 15.0, 6.0, 7.0], Add())


class TestScalar:
    @pytest.mark.parametrize(
        "factor,expected",
        [
            (2, [2.0, 4.0, 6.0, 8.0, 10.0, 12.0, 14.0]),
            (1, [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0]),
            (0, [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]),
            (-1, [-1.0, -2.0, -3.0, -4.0, -5.0, -6.0, -7.0]),
            (0.5, [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5]),
        ],
    )
    def test_scalar_simple(self, factor: float, expected: list[float]) -> None:
        """Test that the scalar function works across the full DataFrame."""
        run_function_test(factor, expected, Scalar())

    def test_scalar_with_date_filter(self) -> None:
        """Test that the scalar function works with a date filter."""
        run_function_with_date_filter_test(10, [1.0, 2.0, 30.0, 40.0, 50.0, 6.0, 7.0], Scalar())


class TestPower:
    @pytest.mark.parametrize(
        "factor, expected",
        [
            (2, [1.0, 4.0, 9.0, 16.0, 25.0, 36.0, 49.0]),
            (3, [1.0, 8.0, 27.0, 64.0, 125.0, 216.0, 343.0]),
            (1, [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0]),
            (0, [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0]),
            (
                0.5,
                [
                    1.0,
                    1.4142135623730951,
                    1.7320508075688772,
                    2.0,
                    2.23606797749979,
                    2.449489742783178,
                    2.6457513110645907,
                ],
            ),
        ],
    )
    def test_power_simple(self, factor: float, expected: list[float]) -> None:
        """Test that the power function works across the full DataFrame."""
        run_function_test(factor, expected, Power())

    def test_power_with_date_filter(self) -> None:
        """Test that the power function works with a date filter."""
        run_function_with_date_filter_test(2, [1.0, 2.0, 9.0, 16.0, 25.0, 6.0, 7.0], Power())


class TestLWCorrection:
    def test_lw_correction_simple(self) -> None:
        """Test that the lw correction function works across the full DataFrame."""
        lw = create_timeframe([373.9, 381.5, 386.9, 398.9, 387.7, 387.3, 391.8], "lw")
        lw_unc = create_timeframe([-53.24, -56.31, -56.64, -41.11, -64.04, -75.39, -81.5], "lw_unc")
        ta = create_timeframe([20.33, 21.74, 22.79, 22.91, 24.3, 25.72, 27.27], "ta")
        factor = 1.00924
        config = create_method_config(correction_factor=factor, lwin_unc=lw_unc, ta=ta)

        result = LWCorrection().run(lw, config)

        expected_df = create_timeframe(
            [
                366.89501779404736,
                371.93855976840695,
                377.7449872014795,
                394.1243133190569,
                379.22105814566305,
                376.3027264419359,
                379.5942580579116,
            ],
            "lw",
        ).df
        assert_frame_equal(result.df, expected_df)

    def test_lw_correction_with_date_filter(self) -> None:
        """Test that LWCorrection works with a date filter."""
        lw = create_timeframe([373.9, 381.5, 386.9, 398.9, 387.7, 387.3, 391.8], "lw")
        lw_unc = create_timeframe([-53.24, -56.31, -56.64, -41.11, -64.04, -75.39, -81.5], "lwin_unc")
        ta = create_timeframe([20.33, 21.74, 22.79, 22.91, 24.3, 25.72, 27.27], "ta")
        factor = 1.00924

        config = create_method_config(
            correction_factor=factor,
            lwin_unc=lw_unc,
            ta=ta,
            start_date=datetime(2025, 1, 1, 2),
            end_date=datetime(2025, 1, 1, 4, 59),
        )

        result = LWCorrection().run(lw, config)
        expected_df = create_timeframe(
            [373.9, 381.5, 377.7449872014795, 394.1243133190569, 379.22105814566305, 387.3, 391.8], "lw"
        ).df
        assert_frame_equal(result.df, expected_df)


class TestPaCorrection:
    def test_pa_correction_simple(self) -> None:
        """Test that the pa correction function works across the full DataFrame."""
        pa = create_timeframe([1007.504, 1007.391, 1007.359, 1007.334, 1007.262, 1007.194, 1007.213], "pa")
        ta = create_timeframe([12.25, 12.49, 12.58, 12.56, 12.82, 13.18, 13.31], "ta")
        altitude = 74.0
        factor = -5.1
        config = create_method_config(correction_factor=factor, ta=ta, altitude=altitude)

        result = PACorrection().run(pa, config)
        expected_df = create_timeframe(
            [1002.4489, 1002.3359, 1002.3039, 1002.2789, 1002.2069, 1002.1388, 1002.1578], "pa"
        ).df
        assert_frame_equal(result.df, expected_df)

    def test_pa_correction_with_date_filter(self) -> None:
        """Test that the pa correction function works with a date filter."""
        pa = create_timeframe([1007.504, 1007.391, 1007.359, 1007.334, 1007.262, 1007.194, 1007.213], "pa")
        ta = create_timeframe([12.25, 12.49, 12.58, 12.56, 12.82, 13.18, 13.31], "ta")
        altitude = 74.0
        factor = -5.1
        config = create_method_config(
            correction_factor=factor,
            ta=ta,
            altitude=altitude,
            start_date=datetime(2025, 1, 1, 2),
            end_date=datetime(2025, 1, 1, 4, 59),
        )

        result = PACorrection().run(pa, config)
        expected_df = create_timeframe(
            [1007.504, 1007.391, 1002.3039, 1002.2789, 1002.2069, 1007.194, 1007.213], "pa"
        ).df
        assert_frame_equal(result.df, expected_df)


class TestWdCorrection:
    def test_wd_correction_simple(self) -> None:
        """Test that the wd correction function works across the full DataFrame.

        # Input data taken from COSMOS.LEVEL1_SOILMET_30MIN Oracle DB table:
        #   Site: BUNNY,
        #   Dates: [2015-04-08 19:30:00, 2017-06-01 05:00:00, 2020-10-03 03:00:00, 2024-12-03 10:00:00]
        """
        wd = create_timeframe([84.89191, 19.17, 185.9, 103.7], "wd")
        ux = create_timeframe([0.204, 0.94, -3.747, -0.007], "ux")
        uy = create_timeframe([2.324, 0.327, -0.384, 0.027], "uy")
        config = create_method_config(ux=ux, uy=uy)

        result = WDCorrection().run(wd, config)
        expected_df = create_timeframe([95.01655, 160.81863, 354.14864, 75.46554], "wd").df
        assert_frame_equal(result.df, expected_df)


class TestClip:
    def test_clip_simple_min_only(self) -> None:
        """Test clip function works across the full DataFrame.
        Uses made up test values as none of the derivation test values gives negative results"""
        pe = create_timeframe([-2, -1, 0, 1, 2, 3], "pe")
        config = create_method_config(min=0)

        result = Clip().run(pe, config)
        expected_df = create_timeframe([0, 0, 0, 1, 2, 3], "pe").df
        assert_frame_equal(result.df, expected_df)

    def test_clip_simple_max_only(self) -> None:
        """Test clip function works across the full DataFrame.
        Uses made up test values as none of the derivation test values gives negative results"""
        pe = create_timeframe([-2, -1, 0, 1, 2, 3], "pe")
        config = create_method_config(max=0)

        result = Clip().run(pe, config)
        expected_df = create_timeframe([-2, -1, 0, 0, 0, 0], "pe").df
        assert_frame_equal(result.df, expected_df)

    def test_clip_simple_min_and_max(self) -> None:
        """Test clip function works across the full DataFrame.
        Uses made up test values as none of the derivation test values gives negative results"""
        pe = create_timeframe([-2, -1, 0, 1, 2, 3], "pe")
        config = create_method_config(min=-1, max=1)

        result = Clip().run(pe, config)
        expected_df = create_timeframe([-1, -1, 0, 1, 1, 1], "pe").df
        assert_frame_equal(result.df, expected_df)

    def test_clip_simple_no_min_or_max(self) -> None:
        """Test clip function works across the full DataFrame.
        Uses made up test values as none of the derivation test values gives negative results"""
        pe = create_timeframe([-2, -1, 0, 1, 2, 3], "pe")
        config = create_method_config()

        with pytest.raises(ValueError) as excinfo:
            Clip().run(pe, config)
        # expected_df = create_timeframe([-2, -1, 0, 1, 2, 3], "pe").df
        assert str(excinfo.value) == (
            "Missing metadata parameter. At least one threshold must be specified in Clip method"
        )

    def test_clip_simple_min_out_of_range(self) -> None:
        """Test clip function works across the full DataFrame.
        Uses made up test values as none of the derivation test values gives negative results"""
        pe = create_timeframe([-2, -1, 0, 1, 2, 3], "pe")
        config = create_method_config(min=-3)

        result = Clip().run(pe, config)
        expected_df = create_timeframe([-2, -1, 0, 1, 2, 3], "pe").df
        assert_frame_equal(result.df, expected_df)

    def test_clip_simple_max_out_of_range(self) -> None:
        """Test clip function works across the full DataFrame.
        Uses made up test values as none of the derivation test values gives negative results"""
        pe = create_timeframe([-2, -1, 0, 1, 2, 3], "pe")
        config = create_method_config(max=4)

        result = Clip().run(pe, config)
        expected_df = create_timeframe([-2, -1, 0, 1, 2, 3], "pe").df
        assert_frame_equal(result.df, expected_df)

    def test_clip_with_date_filter(self) -> None:
        """Test clip correction function works with a date filter."""
        pe = create_timeframe([-3, -2, -1, 0, 1, 2, 3], "pe")
        config = create_method_config(
            min=0,
            start_date=datetime(2025, 1, 1, 2),
            end_date=datetime(2025, 1, 1, 4, 59),
        )

        result = Clip().run(pe, config)
        expected_df = create_timeframe([-3, -2, 0, 0, 1, 2, 3], "pe").df
        assert_frame_equal(result.df, expected_df)
