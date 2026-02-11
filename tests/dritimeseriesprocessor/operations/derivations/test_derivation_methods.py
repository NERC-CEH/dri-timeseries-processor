from typing import Any

import polars as pl
from polars.testing import assert_frame_equal

from dritimeseriesprocessor.models.domain_models.processing_config import DataProcessingMethodConfig
from dritimeseriesprocessor.operations.derivation.derivation_methods import (
    AbsoluteHumidity,
    DerivationMethod,
    MeanSeaLevelPressure,
    MeanSoilHeatFlux,
    NetRadiation,
    PotentialEvapotranspiration30Min,
)
from utils.data_creation import dataframe_to_timeframe


class SimpleAddition(DerivationMethod):
    name = "add"
    inputs = ("a", "b")

    def expr(self, columns: dict[str, pl.Expr]) -> pl.Expr:
        return columns["a"] + columns["b"]


def create_method_config(data: dict[str, list[float]], output_col: str) -> DataProcessingMethodConfig:
    """Create a test MethodConfig.

    Args:
        data: List of data objects needed for the calculation
        output_col: Name of the output column expected in the result

    Returns:
        MethodConfig for testing
    """
    params: dict[str, Any] = {
        column_name: dataframe_to_timeframe(pl.DataFrame({column_name: values}), metadata={"column_name": column_name})
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
        input_df = pl.DataFrame({"ws": [3.2]})

        calc = PotentialEvapotranspiration30Min().wind_speed_height_correction(pl.col("ws"), 10.0)
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
                "altitude": [0, 1, 2, 3],
            },
            "mslp",
        )

        expected = dataframe_to_timeframe(pl.DataFrame({"mslp": [1024.0, 1011.483, 1033.909, 1021.051]}))

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
