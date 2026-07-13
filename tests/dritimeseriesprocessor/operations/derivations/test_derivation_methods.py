from datetime import datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import polars as pl
import pytest
from polars.testing import assert_frame_equal

from dritimeseriesprocessor.models.domain_models.processing_config import DataProcessingMethodConfig
from dritimeseriesprocessor.operations.derivation.derivation_methods import (
    AbsoluteHumidity,
    AbsoluteHumidityFactor,
    Albedo,
    AtmosphericPressureFactor,
    CalcFluxLeL1,
    CalcFluxMeanShf,
    CorrectCounts,
    DerivationMethod,
    EddyProRun,
    GetSnowEstimatedCounts,
    IsSnowDay,
    MeanSeaLevelPressure,
    MeanSoilHeatFlux,
    NetRadiation,
    NeutronIntensityFactor,
    PotentialEvapotranspiration30Min,
    SolarZenith,
    VolumetricWaterContent,
    VolumetricWaterContentWithSnow,
)
from utils.data_creation import dataframe_to_timeframe


class SimpleAddition(DerivationMethod):
    name = "add"
    inputs = ("a", "b")

    def expr(self, columns: dict[str, pl.Expr]) -> pl.Expr:
        return columns["a"] + columns["b"]


def create_method_config(
    data: dict[str, list[float | None]],
    output_col: str,
) -> DataProcessingMethodConfig:
    """Create a test MethodConfig.

    Args:
        data: List of data objects needed for the calculation
        output_col: Name of the output column expected in the result
        argument: Dict of arguments to add to the config

    Returns:
        MethodConfig for testing
    """
    params: dict[str, Any] = {}
    if data:
        params = {
            column_name: dataframe_to_timeframe(
                df=pl.DataFrame({column_name: values}),
                metadata={"column_name": column_name},
            )
            for column_name, values in data.items()
        }
    params["output_col"] = output_col
    params["periodicity"] = "PT1H"
    params["resolution"] = "PT1H"
    params["time_anchor"] = "start"

    return DataProcessingMethodConfig(method="test", params=params)


class TestDerivationMethod:
    def test_run_simple_addition_calculation(self) -> None:
        """Test a simple addition derivation workflow"""
        method = SimpleAddition()
        config = create_method_config({"a": [10.0, 20.0, 30.0], "b": [5.0, 10.0, 15.0]}, "out")

        result = method.run(config)
        expected = dataframe_to_timeframe(pl.DataFrame({"out": [15.0, 30.0, 45.0]}), metadata={"column_name": "out"})
        assert result == expected


class TestNetRadiation:
    def test_calculation(self) -> None:
        config = create_method_config(
            {
                "swin": [22.9, 19.3, 14, 25.1],
                "swout": [4.9, 4.2, 3, 5.5],
                "lwin": [24.1, 26, 26.2, 23.1],
                "lwout": [31.2, 31.9, 30.9, 30.8],
            },
            "rn",
        )

        expected = dataframe_to_timeframe(pl.DataFrame({"rn": [10.9, 9.2, 6.3, 11.9]}))

        result = NetRadiation().run(config)
        assert_frame_equal(result.df, expected.df, check_exact=False, abs_tol=0.001)


class TestPotentialEvapotranspiration30Min:
    def test_calculation(self) -> None:
        # Taken from COSMOS.LEVEL3_DATA_30MIN Oracle DB view:
        #   Site: CHOBH,
        #   Dates: [2015-03-14 04:30:00, 2017-05-30 16:30:00, 2022-01-18 09:30:00, 2023-08-21 11:00:00]
        config = create_method_config(
            {
                "rn": [-68.181, 302.85, 116.2, 364.6],
                "g": [-29.6453, 32.23711, -23.7416, 16.64824],
                "ta": [1.977, 19.62, -2.144, 20.54],
                "rh": [72.5, 57.62, 95.6, 65.41],
                "ws": [2.89954, 3.204, 0.214, 2.048],
                "pa": [1024.0, 1011.365, 1033.649, 1020.695],
            },
            "pet",
        )

        config.params["wind_height"] = {
            "wind_height.source": "deployment",
            "wind_height.value": [(datetime(1900, 1, 1), None, 2.6)],
        }

        expected = dataframe_to_timeframe(pl.DataFrame({"pet": [0.00573, 0.14733, 0.03617, 0.17283]}))

        result = PotentialEvapotranspiration30Min().run(config)
        assert_frame_equal(result.df, expected.df, check_exact=False, abs_tol=0.001)

    def test_saturation_vapour_pressure(self) -> None:
        # Taken from FAO56 EXAMPLE 3 https://www.fao.org/4/x0490e/x0490e07.htm
        input_df = pl.DataFrame({"ta": [15.0, 24.5]})

        calc = PotentialEvapotranspiration30Min().saturation_vapour_pressure(pl.col("ta"))
        result = input_df.with_columns(calc.alias("es")).select(["es"])
        expected = pl.DataFrame({"es": [1.705, 3.075]})

        assert_frame_equal(result, expected, check_exact=False, abs_tol=0.001)

    def test_actual_vapour_pressure(self) -> None:
        # Taken from FAO56 EXAMPLE 19 https://www.fao.org/4/x0490e/x0490e08.htm
        input_df = pl.DataFrame({"rh": [90, 52], "es": [3.78, 6.625]})

        calc = PotentialEvapotranspiration30Min().actual_vapour_pressure(pl.col("es"), pl.col("rh"))
        result = input_df.with_columns(calc.alias("ea")).select(["ea"])
        expected = pl.DataFrame({"ea": [3.402, 3.445]})

        assert_frame_equal(result, expected, check_exact=False, abs_tol=0.001)

    def test_vapour_pressure_curve_slope(self) -> None:
        # Taken from FAO56 EXAMPLE 18, 19 and 20 https://www.fao.org/4/x0490e/x0490e08.htm
        input_df = pl.DataFrame({"es": [1.997, 2.58, 3.78, 6.625], "ta": [16.9, 20.7, 28, 38]})

        calc = PotentialEvapotranspiration30Min().vapour_pressure_curve_slope(pl.col("es"), pl.col("ta"))
        result = input_df.with_columns(calc.alias("delta")).select(["delta"])
        expected = pl.DataFrame({"delta": [0.122, 0.15, 0.22, 0.358]})

        assert_frame_equal(result, expected, check_exact=False, abs_tol=0.01)

    def test_latent_heat_of_vaporization(self) -> None:
        input_df = pl.DataFrame({"ta": [-20.0, 0.0, 20.0, 100.0]})

        calc = PotentialEvapotranspiration30Min().latent_heat_of_vaporization(pl.col("ta"))
        result = input_df.with_columns(calc.alias("lv")).select(["lv"])
        expected = pl.DataFrame({"lv": [2.54, 2.501, 2.45, 2.26]})

        assert_frame_equal(result, expected, check_exact=False, abs_tol=0.01)

    def test_psychrometric_constant(self) -> None:
        # Taken from FAO56 EXAMPLE 2 https://www.fao.org/4/x0490e/x0490e07.htm#psychrometric%20constant%20(g)
        # Taken from FAO56 EXAMPLE 18 https://www.fao.org/4/x0490e/x0490e08.htm
        input_df = pl.DataFrame({"lv": [2.45, 2.46], "pa": [1001.0, 818.0]})

        calc = PotentialEvapotranspiration30Min().psychrometric_constant(pl.col("pa"), pl.col("lv"))
        result = input_df.with_columns(calc.alias("gamma")).select(["gamma"])
        expected = pl.DataFrame({"gamma": [0.066, 0.054]})

        assert_frame_equal(result, expected, check_exact=False, abs_tol=0.001)

    def test_wind_speed_height_correction(self) -> None:
        # Taken from FAO56 EXAMPLE 14 https://www.fao.org/4/x0490e/x0490e07.htm#wind%20profile%20relationship
        input_df = pl.DataFrame({"ws": [3.2], "height": [10.0]})

        calc = PotentialEvapotranspiration30Min().wind_speed_height_correction(pl.col("ws"), pl.col("height"))
        result = input_df.with_columns(calc.alias("ws2m")).select(["ws2m"])
        expected = pl.DataFrame({"ws2m": [2.4]})

        assert_frame_equal(result, expected, check_exact=False, abs_tol=0.01)


class TestMeanSoilHeatFlux:
    def test_calculation(self) -> None:
        """Test mean soil heat flux (G) calculation - should just be a simple average between G1 and G2."""
        config = create_method_config(
            {
                "g1": [1.5, 10.9, 123.4],
                "g2": [-7.9, 0.01, 985.36],
            },
            "g",
        )

        expected = dataframe_to_timeframe(pl.DataFrame({"g": [-3.2, 5.455, 554.38]}))

        result = MeanSoilHeatFlux().run(config)
        assert_frame_equal(result.df, expected.df, check_exact=False, abs_tol=0.001)


class TestMeanSeaLevelPressure:
    def test_calculation(self) -> None:
        """Test mean sea level pressure (mslp) calculation - a simple calculation with pa and ta."""
        config = create_method_config(
            {
                "ta": [1.977, 19.62, -2.144, 20.54],
                "pa": [1024.0, 1011.365, 1033.649, 1020.695],
            },
            "mslp",
        )
        config.params["altitude"] = 74  # [M] holln

        expected = dataframe_to_timeframe(pl.DataFrame({"mslp": [1033.446, 1020.131, 1043.330, 1029.514]}))

        result = MeanSeaLevelPressure().run(config)
        assert_frame_equal(result.df, expected.df, check_exact=False, abs_tol=0.001)


class TestAbsoluteHumidity:
    def test_calculation(self) -> None:
        """Test absolute humidity (Q) calculation."""
        config = create_method_config(
            {
                "ta": [1.977, 19.62, -2.144, 20.54],
                "rh": [72.5, 57.62, 95.6, 65.41],
            },
            "q",
        )

        expected = dataframe_to_timeframe(pl.DataFrame({"q": [4.025, 9.736, 3.994, 11.664]}))

        result = AbsoluteHumidity().run(config)
        assert_frame_equal(result.df, expected.df, check_exact=False, abs_tol=0.001)


class TestNeutronIntensityFactor:
    def test_calculation(self) -> None:
        """Test incoming neutron intensity factor calculation."""
        config = create_method_config({"crns-count": [150.1, 151.2, 153.3, 154.4]}, "calc_factor_inten")

        config.params["ref_c0"] = 152.03496  # holln
        config.params["gamma"] = 1.29291  # holln

        # Expected values should be positive
        expected = dataframe_to_timeframe(pl.DataFrame({"calc_factor_inten": [1.016, 1.007, 0.989, 0.980]}))
        result = NeutronIntensityFactor().run(config)
        assert_frame_equal(result.df, expected.df, check_exact=False, abs_tol=0.001)


class TestAbsoluteHumidityFactor:
    def test_calculation(self) -> None:
        """Test absolute humidity correction factor calculation."""
        config = create_method_config(
            {
                "q": [4.025, 9.736, 3.994, 11.664],
            },
            "factor_q",
        )
        config.params["ref_q0"] = 8.27  # [g m-3] holln

        expected = dataframe_to_timeframe(pl.DataFrame({"factor_q": [0.97707, 1.00791, 0.97690, 1.01832]}))
        result = AbsoluteHumidityFactor().run(config)
        assert_frame_equal(result.df, expected.df, check_exact=False, abs_tol=0.00001)


class TestAtmosphericPressureFactor:
    def test_calculation(self) -> None:
        """Test atmospheric pressure factor calculation."""
        config = create_method_config(
            {"pa": [1024.0, 1011.365, 1033.649, 1020.695]},
            "factor_pa",
        )
        config.params["l"] = 137.04156  # [M] holln

        expected = dataframe_to_timeframe(pl.DataFrame({"factor_pa": [1.1914, 1.08646, 1.27831, 1.16301]}))
        result = AtmosphericPressureFactor().run(config)
        assert_frame_equal(result.df, expected.df, check_exact=False, abs_tol=0.00001)


class TestSolarZenith:
    def test_solar_zenith(self) -> None:
        """Test solar zenith calculation
        Only datetimes and latitude are used.
        To test this method, both day and night times should be used.
        """
        config = create_method_config({"swin": list(map(float, range(24)))}, "solar_zenith")
        config.params["lat"] = 54.110665  # [degrees] holln

        expected = dataframe_to_timeframe(
            pl.DataFrame(
                {
                    "solar_zenith": [
                        2.599,
                        2.564,
                        2.472,
                        2.343,
                        2.198,
                        2.045,
                        1.893,
                        1.749,
                        1.618,
                        1.506,
                        1.419,
                        1.365,
                        1.346,
                        1.365,
                        1.419,
                        1.506,
                        1.617,
                        1.749,
                        1.893,
                        2.045,
                        2.197,
                        2.344,
                        2.472,
                        2.564,
                    ]
                }
            )
        )

        result = SolarZenith().run(config)
        assert_frame_equal(result.df, expected.df, check_exact=False, abs_tol=0.001)


class TestAlbedo:
    def test_albedo(self) -> None:
        """Test albedo calculation.
        Use fictitious test data, not enough test data available. Data was randomly generated.
        To test this method, both day and night times should be used."""
        config = create_method_config(
            {
                "swin": [
                    22.9,
                    17.7,
                    21.0,
                    26.0,
                    15.5,
                    18.5,
                    22.0,
                    24.2,
                    20.6,
                    20.2,
                    24.6,
                    16.6,
                    26.9,
                    17.1,
                    23.1,
                    17.2,
                    13.9,
                    21.1,
                    25.5,
                    20.9,
                    15.0,
                    16.6,
                    21.2,
                    18.0,
                ],
                "swout": [
                    2.6,
                    4.0,
                    5.6,
                    3.0,
                    5.9,
                    2.8,
                    4.0,
                    5.4,
                    3.8,
                    3.7,
                    4.2,
                    3.8,
                    5.0,
                    4.7,
                    5.7,
                    3.0,
                    2.6,
                    5.4,
                    3.0,
                    4.5,
                    3.3,
                    5.7,
                    5.5,
                    4.3,
                ],
                "solar_zenith": [
                    2.599,
                    2.564,
                    2.472,
                    2.343,
                    2.198,
                    2.045,
                    1.893,
                    1.749,
                    1.618,
                    1.506,
                    1.419,
                    1.365,
                    1.346,
                    1.365,
                    1.419,
                    1.506,
                    1.617,
                    1.749,
                    1.893,
                    2.045,
                    2.197,
                    2.344,
                    2.472,
                    2.564,
                ],
            },
            "albedo",
        )

        expected = dataframe_to_timeframe(
            pl.DataFrame(
                {
                    "albedo": [
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        0.183,
                        0.171,
                        0.229,
                        0.186,
                        0.275,
                        0.247,
                        0.174,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                    ]
                }
            )
        )

        result = Albedo().run(config)
        assert_frame_equal(result.df, expected.df, check_exact=False, abs_tol=0.001)


class TestIsSnowDay:
    def test_is_snow_day(self) -> None:
        """
        Test calculation that checks if it is a snow day
        All possible combinations are tested.
        """
        config = create_method_config(
            {
                "albedo": [
                    None,
                    0.20,
                    None,
                    0.40,
                    None,
                    0.60,
                    0.10,
                    None,
                    0.10,
                    0.20,
                    0.10,
                    0.40,
                    0.10,
                    0.60,
                    0.45,
                    None,
                    0.45,
                    0.20,
                    0.45,
                    0.40,
                    0.45,
                    0.60,
                    0.65,
                    None,
                    0.65,
                    0.20,
                    0.65,
                    0.40,
                    0.65,
                    0.60,
                ]
            },
            "is_snow_day",
        )
        config.params["albedo_min_threshold"] = 0.35
        config.params["albedo_max_threshold"] = 0.5

        expected = dataframe_to_timeframe(
            pl.DataFrame(
                {
                    "is_snow_day": [
                        None,
                        False,
                        None,
                        None,
                        None,
                        True,
                        False,
                        None,
                        False,
                        False,
                        False,
                        False,
                        False,
                        True,
                        True,
                        None,
                        None,
                        False,
                        False,
                        False,
                        False,
                        True,
                        True,
                        None,
                        True,
                        False,
                        True,
                        True,
                        True,
                        True,
                    ]
                }
            )
        )
        result = IsSnowDay().run(config)
        assert_frame_equal(result.df, expected.df)


class TestCorrectCounts:
    def test_correct_counts(self) -> None:
        """Test corrected mod counts are the product of raw counts and all three correction factors.
        cts_mod values from cosmos-holln on 2016-07-27.
        Factor values taken from the holln expected outputs in TestNeutronIntensityFactor,
        TestAtmosphericPressureFactor, and TestAbsoluteHumidityFactor.
        """
        config = create_method_config(
            {
                "cts_mod": [749.0, 746.0, 793.0, 734.0],
                "cosmosfactor_inten": [1.016, 1.007, 0.989, 0.980],
                "cosmosfactor_pa": [1.1914, 1.08646, 1.27831, 1.16301],
                "cosmosfactor_q": [0.97707, 1.00791, 0.97690, 1.01832],
            },
            "cts_mod_corr",
        )
        expected = dataframe_to_timeframe(pl.DataFrame({"cts_mod_corr": [885.847, 822.629, 979.390, 851.902]}))
        result = CorrectCounts().run(config)
        assert_frame_equal(result.df, expected.df, check_exact=False, abs_tol=0.01)


class TestVolumetricWaterContent:
    def test_volumetric_water_content(self) -> None:
        """Test calculate_vwc using cosmos-holln site annotations.
        cts_mod_corr values include 0, the corrected counts from TestCorrectCounts (all below n_min),
        and representative valid-range counts.
        """
        config = create_method_config(
            {"cts_mod_corr": [0.0, 885.847, 822.629, 979.390, 851.902, 1300.0, 1500.0, 1800.0, 2000.0]},
            "vwc",
        )
        # Annotations from cosmos-holln
        config.params["n0_mod"] = 2710.16689
        config.params["ref_bulkdensity"] = 1.06
        config.params["ref_latticewater"] = 0.025
        config.params["ref_soc"] = 0.032
        config.params["n_min"] = 1204.50827
        config.params["n_max"] = 2281.33025

        expected = dataframe_to_timeframe(
            pl.DataFrame({"vwc": [100.0, 100.0, 100.0, 100.0, 100.0, 61.311, 28.964, 11.083, 5.172]})
        )
        result = VolumetricWaterContent().run(config)
        assert_frame_equal(result.df, expected.df, check_exact=False, abs_tol=0.1)


class TestGetSnowEstimatedCounts:
    def test_get_snow_estimated_counts(self) -> None:
        """Test get_snow_estimated_counts using fictional data, where snow suppresses the counts.
        This test covers the following cases:
        1. Snow period starts if there is snow on a given day, but there was no snow for at least two days previously.
        2. Snow period ends after two consecutive days of now snow.
        3. During snow period, counts should be the maximum of either:
                the value of the smoothed counts just before the start of the snow period,
            or:
                the value of smoothed counts.
        4. One day of no snow should not be considered the end of the snow period.
        5. If there is a snow day within the first two days of the dataset,
           then there is no data for the previous days to check if it is the start of the snow period,
           so no count estimate is given.
        6. A snow period at the end of the dataset is handled correctly, even if event_end.shift(-24) is null.
        """
        daily_cts_smo = [995.0, 1000, 1002, 995, 996, 1003, 997, 1001, 1002, 1003, 995]

        params = {
            "cts_smo": dataframe_to_timeframe(
                df=pl.DataFrame({"cts_smo": [i for item in daily_cts_smo for i in [item] * 24]}),
                metadata={"column_name": "cts_smo"},
            ),
            "snow": dataframe_to_timeframe(
                df=pl.DataFrame(
                    {
                        "snow": [1, 0, 0, 1, 1, 0, 1, 0, 0, 1, 1],
                        "time": [datetime(2025, 1, i) for i in range(1, 12)],
                    }
                ),
                metadata={"column_name": "snow"},
                resolution="P1D",
            ),
        }

        config = DataProcessingMethodConfig(method="test", params=params)

        daily_cts_est = [
            None,
            None,
            None,
            1002.0,
            1002.0,
            1003.0,
            1002.0,
            None,
            None,
            1003.0,
            1002.0,
        ]

        expected = dataframe_to_timeframe(pl.DataFrame({"cts_est": [i for item in daily_cts_est for i in [item] * 24]}))
        result = GetSnowEstimatedCounts().run(config)
        assert_frame_equal(result.df, expected.df, check_exact=False, abs_tol=0.1)

    def test_all_snow(self) -> None:
        """Test no counts are estimated if the entire dataset consists of snow days. Since we don't know when
        the snow period started, we cannot use the counts from before the snow period as an estimate."""
        daily_cts_smo = [995.0, 996, 997, 998]

        params = {
            "cts_smo": dataframe_to_timeframe(
                df=pl.DataFrame({"cts_smo": [i for item in daily_cts_smo for i in [item] * 24]}),
                metadata={"column_name": "cts_smo"},
            ),
            "snow": dataframe_to_timeframe(
                df=pl.DataFrame(
                    {
                        "snow": [1, 1, 1, 1],
                        "time": [datetime(2025, 1, i) for i in range(1, 5)],
                    }
                ),
                metadata={"column_name": "snow"},
                resolution="P1D",
            ),
        }

        config = DataProcessingMethodConfig(method="test", params=params)

        daily_cts_est = [None, None, None, None]

        expected = dataframe_to_timeframe(
            pl.DataFrame(
                {"cts_est": [i for item in daily_cts_est for i in [item] * 24]}, schema={"cts_est": pl.Float64}
            )
        )
        result = GetSnowEstimatedCounts().run(config)
        assert_frame_equal(result.df, expected.df, check_exact=False, abs_tol=0.1)

    def test_no_snow(self) -> None:
        """Test no counts are estimated the the entire dataset consists of no snow days."""
        daily_cts_smo = [1000.0, 1001, 1002, 1003]

        params = {
            "cts_smo": dataframe_to_timeframe(
                df=pl.DataFrame({"cts_smo": [i for item in daily_cts_smo for i in [item] * 24]}),
                metadata={"column_name": "cts_smo"},
            ),
            "snow": dataframe_to_timeframe(
                df=pl.DataFrame(
                    {
                        "snow": [0, 0, 0, 0],
                        "time": [datetime(2025, 1, i) for i in range(1, 5)],
                    }
                ),
                metadata={"column_name": "snow"},
                resolution="P1D",
            ),
        }

        config = DataProcessingMethodConfig(method="test", params=params)

        daily_cts_est = [None, None, None, None]

        expected = dataframe_to_timeframe(
            pl.DataFrame(
                {"cts_est": [i for item in daily_cts_est for i in [item] * 24]}, schema={"cts_est": pl.Float64}
            )
        )
        result = GetSnowEstimatedCounts().run(config)
        assert_frame_equal(result.df, expected.df, check_exact=False, abs_tol=0.1)

    def test_null_snow_values(self) -> None:
        """
        Test where snow is null, followed by 0, followed by 1, the latter is not considered start of a snow period.
        Test where snow is null within a snow period, estimated counts still propegate.
        """
        daily_cts_smo = [995.0, 1000, 995, 1003, 1001, 1002, 995, 996]

        params = {
            "cts_smo": dataframe_to_timeframe(
                df=pl.DataFrame({"cts_smo": [i for item in daily_cts_smo for i in [item] * 24]}),
                metadata={"column_name": "cts_smo"},
            ),
            "snow": dataframe_to_timeframe(
                df=pl.DataFrame(
                    {
                        "snow": [None, 0, 1, 0, 0, 1, None, 1],
                        "time": [datetime(2025, 1, i) for i in range(1, 9)],
                    }
                ),
                metadata={"column_name": "snow"},
                resolution="P1D",
            ),
        }

        config = DataProcessingMethodConfig(method="test", params=params)

        daily_cts_est = [
            None,
            None,
            None,
            None,
            None,
            1002.0,
            1001.0,
            1001.0,
        ]

        expected = dataframe_to_timeframe(pl.DataFrame({"cts_est": [i for item in daily_cts_est for i in [item] * 24]}))
        result = GetSnowEstimatedCounts().run(config)
        assert_frame_equal(result.df, expected.df, check_exact=False, abs_tol=0.1)

    def test_null_cts(self) -> None:
        """
        Test null counts remain null when not in a snow period.
        Test null counts are filled with an estimated if during a snow period.
        """
        daily_cts_smo = [1000.0, None, 1001, 1002, 995, None, 996]

        params = {
            "cts_smo": dataframe_to_timeframe(
                df=pl.DataFrame({"cts_smo": [i for item in daily_cts_smo for i in [item] * 24]}),
                metadata={"column_name": "cts_smo"},
            ),
            "snow": dataframe_to_timeframe(
                df=pl.DataFrame(
                    {
                        "snow": [0, 0, 0, 0, 1, 1, 1],
                        "time": [datetime(2025, 1, i) for i in range(1, 8)],
                    }
                ),
                metadata={"column_name": "snow"},
                resolution="P1D",
            ),
        }

        config = DataProcessingMethodConfig(method="test", params=params)

        daily_cts_est = [
            None,
            None,
            None,
            None,
            1002.0,
            1002.0,
            1002.0,
        ]

        expected = dataframe_to_timeframe(pl.DataFrame({"cts_est": [i for item in daily_cts_est for i in [item] * 24]}))
        result = GetSnowEstimatedCounts().run(config)
        assert_frame_equal(result.df, expected.df, check_exact=False, abs_tol=0.1)

    def test_hourly_variation_in_cts_smo(self) -> None:
        """
        Test the initial count estimated is from the *last hour* of the day before the snow period starts.
        Test cts_est is compared against cts_smo hour-by-hour, not just once per day.
        """
        filler_day = [900.0] * 24  # values never read, just needs snow=0 two days before the period
        pre_period_day = [901.0 + h for h in range(24)]  # last hour (924.0) becomes the initial estimate
        snow_start_day = [900.0] * 12 + [950.0] * 12
        cts_smo = filler_day + pre_period_day + snow_start_day

        params = {
            "cts_smo": dataframe_to_timeframe(
                df=pl.DataFrame({"cts_smo": cts_smo}),
                metadata={"column_name": "cts_smo"},
            ),
            "snow": dataframe_to_timeframe(
                df=pl.DataFrame(
                    {
                        "snow": [0, 0, 1],
                        "time": [datetime(2025, 1, i) for i in range(1, 4)],
                    }
                ),
                metadata={"column_name": "snow"},
                resolution="P1D",
            ),
        }

        config = DataProcessingMethodConfig(method="test", params=params)

        cts_est = [None] * 24 + [None] * 24 + [924.0] * 12 + [950.0] * 12

        expected = dataframe_to_timeframe(pl.DataFrame({"cts_est": cts_est}))
        result = GetSnowEstimatedCounts().run(config)
        assert_frame_equal(result.df, expected.df, check_exact=False, abs_tol=0.1)


class TestVolumetricWaterContentWithSnow:
    """Test calculation for volumetric water content when there is snow, using fictional data."""

    def test_vwc_with_snow(self) -> None:
        daily_cts_mod_corr = [1300.0, 1295, 1298, 1280, 1280]  # Suppression of counts by snow
        daily_cts_est_crns = [None, None, 1298.0, 1280, 1280]
        config = create_method_config(
            {
                "cts_mod_corr": [i for item in daily_cts_mod_corr for i in [item] * 24],
                "cts_est_crns": [i for item in daily_cts_est_crns for i in [item] * 24],
            },
            "vwc_with_snow",
        )

        # Annotations from cosmos-holln
        config.params["n0_mod"] = 2710.16689
        config.params["ref_bulkdensity"] = 1.06
        config.params["ref_latticewater"] = 0.025
        config.params["ref_soc"] = 0.032
        config.params["n_min"] = 1204.50827
        config.params["n_max"] = 2281.33025

        expected_daily_vwc_with_snow = [61.31088, 62.69752, 61.85980, 67.16354, 67.16354]
        expected_vwc_with_snow = [i for item in expected_daily_vwc_with_snow for i in [item] * 24]

        # Do we need the annotations?
        result = VolumetricWaterContentWithSnow().run(config)
        assert [round(item, 5) for item in list(result.df["vwc_with_snow"])] == expected_vwc_with_snow


class TestCalcFluxMeanShf:
    def test_averages_two_shf_plates(self) -> None:
        config = create_method_config(
            {"g_plate_1_1_1": [10.0, 20.0], "g_plate_1_1_2": [30.0, 40.0]},
            "shf",
        )
        result = CalcFluxMeanShf().run(config)
        assert list(result.df["shf"]) == [20.0, 30.0]

    def test_null_in_one_plate_returns_non_null_value(self) -> None:
        config = create_method_config(
            {"g_plate_1_1_1": [None, 20.0], "g_plate_1_1_2": [10.0, None]},
            "shf",
        )
        result = CalcFluxMeanShf().run(config)
        assert result.df["shf"][0] == 10.0
        assert result.df["shf"][1] == 20.0


class TestCalcFluxLeL1:
    def test_le_equals_rn_minus_shf_minus_h(self) -> None:
        # LE_L1 = Rn - SHF - H  →  300 - 50 - 100 = 150
        config = create_method_config(
            {"t_nr_avg": [300.0], "shf": [50.0], "h": [100.0]},
            "le",
        )
        result = CalcFluxLeL1().run(config)
        assert result.df["le"][0] == 150.0

    def test_null_propagates(self) -> None:
        config = create_method_config(
            {"t_nr_avg": [None], "shf": [50.0], "h": [100.0]},
            "le",
        )
        result = CalcFluxLeL1().run(config)
        assert result.df["le"][0] is None


def _make_eddypro_config(
    container: MagicMock,
    dataset_repository: dict,
    start_date: datetime = datetime(2024, 1, 1),
    end_date: datetime = datetime(2024, 1, 31),
    site_metadata: dict | None = None,
    file_duration: int = 30,
) -> DataProcessingMethodConfig:
    return DataProcessingMethodConfig(
        method="eddypro-run",
        params={
            "container": container,
            "dataset_repository": dataset_repository,
            "processing_start_date": start_date,
            "processing_end_date": end_date,
            "site_metadata": site_metadata or {},
            "file_duration": file_duration,
        },
    )


class TestEddyProRun:
    def test_raises_when_no_base_dependency(self) -> None:
        """Tests that a ValueError is raised when the container has no base dependency."""
        container = MagicMock()
        container.base_dependency = []

        config = _make_eddypro_config(container, {})

        with pytest.raises(ValueError):
            EddyProRun().run(config)

    def test_raises_when_multiple_base_dependencies(self) -> None:
        """Tests that a ValueError is raised when the container has more than one base dependency."""
        container = MagicMock()
        container.base_dependency = ["dep-1", "dep-2"]

        config = _make_eddypro_config(container, {"dep-1": MagicMock(), "dep-2": MagicMock()})

        with pytest.raises(ValueError):
            EddyProRun().run(config)

    def test_raises_when_staged_dir_is_none(self) -> None:
        """Tests that a ValueError is raised when the raw dependency has not been staged locally."""
        container = MagicMock()
        container.base_dependency = ["raw-dep"]
        raw_dep = MagicMock()
        raw_dep.staged_dir = None
        raw_dep.ts_id = "raw-dep"

        config = _make_eddypro_config(container, {"raw-dep": raw_dep})

        with pytest.raises(ValueError):
            EddyProRun().run(config)

    def test_calls_pipeline_with_staged_dir_and_date_range(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Tests that EddyProPipeline.run is called with the raw staged directory and the date range."""
        container = MagicMock()
        container.base_dependency = ["raw-dep"]
        container.all_dependencies.return_value = ["raw-dep"]
        container.source_site = "flux-plynl"
        raw_dep = MagicMock()
        raw_dep.staged_dir = tmp_path
        raw_dep.ts_id = "raw-dep"

        start = datetime(2024, 1, 1)
        end = datetime(2024, 1, 31)

        mock_pipeline = MagicMock()
        mock_pipeline.run.return_value = pl.DataFrame({"time": []})
        monkeypatch.setattr(
            "dritimeseriesprocessor.operations.derivation.derivation_methods.EddyProRunner",
            MagicMock,
        )
        monkeypatch.setattr(
            "dritimeseriesprocessor.operations.derivation.derivation_methods.EddyProPipeline",
            lambda *args, **kwargs: mock_pipeline,
        )

        EddyProRun().run(_make_eddypro_config(container, {"raw-dep": raw_dep}, start_date=start, end_date=end))

        call_kwargs = mock_pipeline.run.call_args.kwargs
        assert call_kwargs["raw_data_dir"] == tmp_path
        assert call_kwargs["start_date"] == start
        assert call_kwargs["end_date"] == end

    def test_sets_container_resolution_from_file_duration(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Tests that the container's resolution and periodicity are set from the file_duration param."""
        container = MagicMock()
        container.base_dependency = ["raw-dep"]
        container.all_dependencies.return_value = ["raw-dep"]
        container.source_site = "flux-plynl"
        raw_dep = MagicMock()
        raw_dep.staged_dir = tmp_path
        raw_dep.ts_id = "raw-dep"

        mock_pipeline = MagicMock()
        mock_pipeline.run.return_value = pl.DataFrame({"time": []})
        monkeypatch.setattr(
            "dritimeseriesprocessor.operations.derivation.derivation_methods.EddyProRunner",
            MagicMock,
        )
        monkeypatch.setattr(
            "dritimeseriesprocessor.operations.derivation.derivation_methods.EddyProPipeline",
            lambda *args, **kwargs: mock_pipeline,
        )

        EddyProRun().run(_make_eddypro_config(container, {"raw-dep": raw_dep}, file_duration=30))

        assert container.time_column_name == "time"
        assert container.resolution == "PT30M"
        assert container.periodicity == container.resolution

    def test_returns_container_data(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """Tests that the method returns the container's data after init_timeframe is called."""
        container = MagicMock()
        container.base_dependency = ["raw-dep"]
        container.all_dependencies.return_value = ["raw-dep"]
        container.source_site = "flux-plynl"
        raw_dep = MagicMock()
        raw_dep.staged_dir = tmp_path
        raw_dep.ts_id = "raw-dep"

        mock_pipeline = MagicMock()
        mock_pipeline.run.return_value = pl.DataFrame({"time": []})
        monkeypatch.setattr(
            "dritimeseriesprocessor.operations.derivation.derivation_methods.EddyProRunner",
            MagicMock,
        )
        monkeypatch.setattr(
            "dritimeseriesprocessor.operations.derivation.derivation_methods.EddyProPipeline",
            lambda *args, **kwargs: mock_pipeline,
        )

        result = EddyProRun().run(_make_eddypro_config(container, {"raw-dep": raw_dep}))

        container.init_timeframe.assert_called_once()
        assert result == container.data
