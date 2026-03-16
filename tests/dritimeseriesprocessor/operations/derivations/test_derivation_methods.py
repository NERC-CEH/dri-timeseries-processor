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
    DerivationMethod,
    MeanSeaLevelPressure,
    MeanSoilHeatFlux,
    NetRadiation,
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
    time_shift: int = 0,
) -> DataProcessingMethodConfig:
    """Create a test MethodConfig.

    Args:
        data: List of data objects needed for the calculation
        output_col: Name of the output column expected in the result
        argument: Dict of arguments to add to the config

    Returns:
        MethodConfig for testing
    """
    params: dict[str, Any] = {
        column_name: dataframe_to_timeframe(
            df=pl.DataFrame({column_name: values}),
            metadata={"column_name": column_name},
            time_shift=time_shift,
        )
        for column_name, values in data.items()
    }
    params["output_col"] = output_col
    params["periodicity"] = "PT1H"
    params["resolution"] = "PT1H"

    # cosmos-holln site attributes/annotations
    params["altitude"] = 74  # [M]
    params["L"] = 137.04156  # [M]
    params["lat"] = 54.110665  # [degrees]
    params["REF_Q0"] = 8.27  # [g m-3]

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


class TestAbsoluteHumidityFactor:
    def test_calculation(self) -> None:
        """Test absolute humidity correction factor calculation."""
        config = create_method_config(
            {
                "q": [4.025, 9.736, 3.994, 11.664],
            },
            "factor_q",
        )

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

        expected = dataframe_to_timeframe(pl.DataFrame({"factor_pa": [1.1914, 1.08646, 1.27831, 1.16301]}))
        result = AtmosphericPressureFactor().run(config)
        assert_frame_equal(result.df, expected.df, check_exact=False, abs_tol=0.00001)


class TestSolarZenith:
    def test_albedo(self) -> None:
        """Test solar zenith calculation
        Using fictitious data as swin data is not used, only datetimes amd latitude are used.
        To test this method, both day and night times should be used.
        """
        config = create_method_config(
            {"swin": list(map(float, range(24)))},
            "solar_zenith",
        )

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
        Use fictitious test data, not enough test data available.
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
