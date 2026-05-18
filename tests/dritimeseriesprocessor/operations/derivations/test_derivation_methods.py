from datetime import datetime
from typing import Any

import polars as pl
from polars.testing import assert_frame_equal

from dritimeseriesprocessor.models.domain_models.processing_config import DataProcessingMethodConfig
from dritimeseriesprocessor.operations.derivation.derivation_methods import (
    AbsoluteHumidity,
    AbsoluteHumidityFactor,
    Albedo,
    AtmosphericPressureFactor,
    CorrectCounts,
    DerivationMethod,
    IsSnowDay,
    MeanSeaLevelPressure,
    MeanSoilHeatFlux,
    NetRadiation,
    NeutronIntensityFactor,
    PotentialEvapotranspiration30Min,
    SolarZenith,
)
from utils.data_creation import dataframe_to_timeframe


class SimpleAddition(DerivationMethod):
    name = "add"
    inputs = ("a", "b")

    def expr(self, columns: dict[str, pl.Expr]) -> pl.Expr:
        return columns["a"] + columns["b"]


def create_method_config(
    data: dict[str, list[float]],
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
    def test_calculation(self) -> None:
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
            "correct_counts",
        )
        expected = dataframe_to_timeframe(pl.DataFrame({"correct_counts": [885.847, 822.629, 979.390, 851.902]}))
        result = CorrectCounts().run(config)
        assert_frame_equal(result.df, expected.df, check_exact=False, abs_tol=0.01)
