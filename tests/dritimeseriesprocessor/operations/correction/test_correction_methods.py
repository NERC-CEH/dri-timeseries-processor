from datetime import datetime

import polars as pl
import pytest
from polars.testing import assert_frame_equal

from dritimeseriesprocessor.models.domain_models.processing_config import DataProcessingMethodConfig
from dritimeseriesprocessor.operations.correction.correction_methods import (
    Absolute,
    Add,
    AlbedoSouthSlopeCorrection,
    Clip,
    CorrectionMethod,
    LWCorrection,
    PACorrection,
    Power,
    Scalar,
    WDCorrection,
)
from utils.data_creation import create_timeframe, dataframe_to_timeframe


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


class TestAbsolute:
    def test_add_simple(self) -> None:
        """Test that the add function works across the full DataFrame."""
        tf = create_timeframe([1.2, -2.1, -3.0, 4.5, 6.0, -2.0, 0.0])
        config = create_method_config()
        result = Absolute().run(tf, config)
        expected_df = pl.DataFrame(
            {"time": [datetime(2025, 1, 1, h) for h in range(7)], "value": [1.2, 2.1, 3.0, 4.5, 6.0, 2.0, 0.0]}
        )
        assert_frame_equal(result.df, expected_df)

    def test_add_with_date_filter(self) -> None:
        """Test that the add function works with a date filter."""
        tf = create_timeframe([1.2, -2.1, -3.0, 4.5, 6.0, -2.0, 0.0])
        config = create_method_config(
            start_date=datetime(2025, 1, 1, 2),
            end_date=datetime(2025, 1, 1, 4, 59),
        )
        result = Absolute().run(tf, config)
        expected_df = pl.DataFrame(
            {"time": [datetime(2025, 1, 1, h) for h in range(7)], "value": [1.2, -2.1, 3.0, 4.5, 6.0, -2.0, 0.0]}
        )
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
        ta = create_timeframe(
            [20.33, 21.74, 22.79, 22.91, 24.3, 25.72, 27.27], "ta", "http://fdri.ceh.ac.uk/ref/common/unit/degc"
        )
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

    def test_lw_correction_simple_kelvin(self) -> None:
        """Test that the lw correction function works across the full DataFrame."""
        lw = create_timeframe([373.9, 381.5, 386.9, 398.9, 387.7, 387.3, 391.8], "lw")
        lw_unc = create_timeframe([-53.24, -56.31, -56.64, -41.11, -64.04, -75.39, -81.5], "lw_unc")
        ta = create_timeframe(
            [293.48, 294.89, 295.94, 296.06, 297.45, 298.87, 300.42], "ta", "http://fdri.ceh.ac.uk/ref/common/unit/kel"
        )
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
        ta = create_timeframe(
            [20.33, 21.74, 22.79, 22.91, 24.3, 25.72, 27.27], "ta", "http://fdri.ceh.ac.uk/ref/common/unit/degc"
        )
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

    def test_lw_correction_no_unc_dependant(self) -> None:
        """Test that the lw correction function works across the full DataFrame."""
        lw = create_timeframe(
            [-38.14216, -38.28978, -40.08758, -40.57142, -41.9975, -43.12814, -44.89819], "R_LW_out_Avg"
        )
        ta = create_timeframe(
            [287.2861, 287.2568, 287.305, 287.2736, 287.1685, 287.0863, 287.0037],
            "T_nr_Avg",
            "http://fdri.ceh.ac.uk/ref/common/unit/kel",
        )
        factor = 1.0
        config = create_method_config(
            correction_factor=factor,
            ta=ta,
            start_date=datetime(2025, 1, 1, 2),
            end_date=datetime(2025, 1, 1, 4, 59),
        )

        result = LWCorrection().run(lw, config)
        expected_df = create_timeframe(
            [-38.14216, -38.28978, 346.2400728, 345.5873711, 343.5964913, -43.12814, -44.89819], "R_LW_out_Avg"
        ).df
        assert_frame_equal(result.df, expected_df)


class TestLWCorrectionDependencyAlignment:
    def test_dependency_covering_fewer_time_values(self) -> None:
        """Tests that a ta dataset covering fewer time values than lw is matched up by time, not by position."""
        lw = create_timeframe([373.9, 381.5, 386.9], "lw")
        lw_unc = create_timeframe([-53.24, -56.31, -56.64], "lw_unc")
        ta = create_timeframe([20.33, 21.74], "ta", unit="http://fdri.ceh.ac.uk/ref/common/unit/degc")
        config = create_method_config(correction_factor=1.00924, lwin_unc=lw_unc, ta=ta)

        result = LWCorrection().run(lw, config)

        assert result.df["lw"][0] == pytest.approx(366.89501779404736)
        assert result.df["lw"][1] == pytest.approx(371.93855976840695)
        assert result.df["lw"][2] is None


class TestPaCorrectionDependencyAlignment:
    def test_dependency_covering_fewer_time_values(self) -> None:
        """Tests that a ta dataset covering fewer time values than pa is matched up by time, not by position."""
        pa = create_timeframe([1007.504, 1007.391, 1007.359], "pa")
        ta = create_timeframe([12.25, 12.49], "ta")
        config = create_method_config(correction_factor=-5.1, ta=ta, altitude=74.0)

        result = PACorrection().run(pa, config)

        assert result.df["pa"][0] == pytest.approx(1002.4489, abs=1e-4)
        assert result.df["pa"][1] == pytest.approx(1002.3359, abs=1e-4)
        assert result.df["pa"][2] is None


class TestWdCorrectionDependencyAlignment:
    def test_dependencies_offset_in_time(self) -> None:
        """Tests that ux and uy datasets starting later than wd are matched up by time, not by position."""
        wd = create_timeframe([84.89191, 19.17, 185.9], "wd")
        # Same values as the aligned test, but shifted an hour later so position and time disagree
        ux = dataframe_to_timeframe(
            pl.DataFrame({"ux": [0.204, 0.94, -3.747]}), metadata={"column_name": "ux"}, time_shift=1
        )
        uy = dataframe_to_timeframe(
            pl.DataFrame({"uy": [2.324, 0.327, -0.384]}), metadata={"column_name": "uy"}, time_shift=1
        )
        config = create_method_config(ux=ux, uy=uy)

        result = WDCorrection().run(wd, config)

        # wd's first time value has no ux/uy, and the rest line up with the first two ux/uy values
        assert result.df["wd"][0] is None
        assert result.df["wd"][1] == pytest.approx(95.016, abs=0.001)
        assert result.df["wd"][2] == pytest.approx(160.819, abs=0.001)


class TestAlbedoSouthSlopeCorrectionDependencyAlignment:
    def test_dependency_covering_fewer_time_values(self) -> None:
        """Tests that a solar zenith dataset covering fewer time values is matched up by time, not by position."""
        albedo = create_timeframe([0.183, 0.171, 0.229], "albedo")
        swin = create_timeframe([20.2, 24.6, 16.6], "swin")
        solar_zenith = create_timeframe([1.506, 1.419], "solar_zenith")
        config = create_method_config(swin=swin, solar_zenith=solar_zenith, theta_g=0.3128764)

        result = AlbedoSouthSlopeCorrection().run(albedo, config)

        assert result.df["albedo"][0] == pytest.approx(0.496, abs=0.001)
        assert result.df["albedo"][1] == pytest.approx(0.381, abs=0.001)
        assert result.df["albedo"][2] is None


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
        expected_df = create_timeframe([95.016, 160.819, 354.148, 75.465], "wd").df
        assert_frame_equal(result.df, expected_df, check_exact=False, abs_tol=0.001)


class TestClip:
    def test_clip_simple_min_only(self) -> None:
        """Test clip function works across the full DataFrame.
        Uses fictitious test values as none of the derivation test values gives negative results"""
        pe = create_timeframe([-2, -1, 0, 1, 2, 3], "pe")
        config = create_method_config(min=0)

        result = Clip().run(pe, config)
        expected_df = create_timeframe([0, 0, 0, 1, 2, 3], "pe").df
        assert_frame_equal(result.df, expected_df)

    def test_clip_simple_max_only(self) -> None:
        """Test clip function works across the full DataFrame.
        Uses fictitious test values as none of the derivation test values gives negative results"""
        pe = create_timeframe([-2, -1, 0, 1, 2, 3], "pe")
        config = create_method_config(max=0)

        result = Clip().run(pe, config)
        expected_df = create_timeframe([-2, -1, 0, 0, 0, 0], "pe").df
        assert_frame_equal(result.df, expected_df)

    def test_clip_simple_min_and_max(self) -> None:
        """Test clip function works across the full DataFrame.
        Uses fictitious test values as none of the derivation test values gives negative results"""
        pe = create_timeframe([-2, -1, 0, 1, 2, 3], "pe")
        config = create_method_config(min=-1, max=1)

        result = Clip().run(pe, config)
        expected_df = create_timeframe([-1, -1, 0, 1, 1, 1], "pe").df
        assert_frame_equal(result.df, expected_df)

    def test_clip_simple_no_min_or_max(self) -> None:
        """Test clip function works across the full DataFrame.
        Uses fictitious test values as none of the derivation test values gives negative results"""
        pe = create_timeframe([-2, -1, 0, 1, 2, 3], "pe")
        config = create_method_config()

        with pytest.raises(ValueError) as excinfo:
            Clip().run(pe, config)
        assert str(excinfo.value) == (
            "Missing metadata parameter. At least one threshold must be specified in Clip method"
        )

    def test_clip_simple_min_out_of_range(self) -> None:
        """Test clip function works across the full DataFrame.
        Uses fictitious test values as none of the derivation test values gives negative results"""
        pe = create_timeframe([-2, -1, 0, 1, 2, 3], "pe")
        config = create_method_config(min=-3)

        result = Clip().run(pe, config)
        expected_df = create_timeframe([-2, -1, 0, 1, 2, 3], "pe").df
        assert_frame_equal(result.df, expected_df)

    def test_clip_simple_max_out_of_range(self) -> None:
        """Test clip function works across the full DataFrame.
        Uses fictitious test values as none of the derivation test values gives negative results"""
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


class TestAlbedoSouthSlopeCorrection:
    def test_albedo_south_slope_correction(self) -> None:
        """Test albedo south slope correction works across the full dataframe.
        The albedo and solar zenith data were obtained from their respective derivation method tests,
        which were generated using fictitious data.
        To test this method, both day and night times should be used.
        """
        swin = create_timeframe(
            [
                20.6,
                20.2,
                24.6,
                16.6,
                26.9,
                17.1,
                23.1,
                17.2,
                13.9,
            ],
            "swin",
        )
        albedo = create_timeframe([None, 0.183, 0.171, 0.229, 0.186, 0.275, 0.247, 0.174, None], "albedo")
        solar_zenith = create_timeframe([1.618, 1.506, 1.419, 1.365, 1.346, 1.365, 1.419, 1.506, 1.617], "solar_zenith")

        config = create_method_config(swin=swin, solar_zenith=solar_zenith, theta_g=0.3128764)

        result = AlbedoSouthSlopeCorrection().run(albedo, config)
        expected_df = create_timeframe([None, 0.496, 0.381, 0.462, 0.363, 0.555, 0.551, 0.472, None], "albedo").df
        assert_frame_equal(result.df, expected_df, check_exact=False, abs_tol=0.001)
