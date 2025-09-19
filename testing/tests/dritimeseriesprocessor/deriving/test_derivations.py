from datetime import datetime, timezone

import polars as pl
from polars.testing import assert_frame_equal
from time_stream import Period, TimeSeries

from dritimeseriesprocessor.deriving.calculation import Calculation
from dritimeseriesprocessor.deriving.derivations import (
    ActualVapourPressureFao56Eq54,
    DailyPotentialEvaporation,
    DailyTotalRadiation,
    LatentHeatOfVaporization,
    NetRadiation,
    PotentialEvapotranspiration30Min,
    PsychrometricConstant,
    SaturationVapourPressure,
    VapourPressureCurveSlope,
    WindSpeedHeightCorrection,
    derive,
)
from testing.utils.testing_utils import df_to_ts
from testing.utils.timeseries_test_helper import TimeSeriesTestHelper


def init_timeseries() -> TimeSeries:
    df = pl.DataFrame(
        {
            "time": [datetime(2024, 1, 1), datetime(2024, 1, 2), datetime(2024, 1, 3)],
            "data_col1": [1, 2, 3],
            "data_col2": [4, 5, 6],
        }
    )
    ts = TimeSeries(df, "time")
    return ts


class MockCalculation(Calculation):
    # Zero dependencies
    def __init__(self, column_name: str):
        super().__init__("Mock calculation", column_name, "mock_unit")

    @property
    def default_column_name(self) -> str:
        return "mock_calc"

    def expr(self) -> pl.Expr:
        return pl.lit(42)


class TestDerive:
    def test_derive_calculation(self) -> None:
        """Test that a new timeseries is created when deriving a calculation, with appropriate metadata and data."""
        ts = init_timeseries()
        calc = MockCalculation
        result = derive(ts, calc)

        expected_df = pl.DataFrame(
            {
                "time": [datetime(2024, 1, 1), datetime(2024, 1, 2), datetime(2024, 1, 3)],
                "mock_calc": [42, 42, 42],
            }
        )

        assert "mock_calc" in result.data_columns
        assert result.mock_calc.metadata() == {"units": "mock_unit"}
        assert_frame_equal(result.df, expected_df, check_dtype=False)


class TestLatentHeatOfVaporization:
    def test_calculation(self) -> None:
        ts = df_to_ts(pl.DataFrame({"TA": [-20, 0, 20, 100]}))
        expected = df_to_ts(pl.DataFrame({"LV": [2.54, 2.501, 2.45, 2.26]}))

        calc = LatentHeatOfVaporization("TA", column_name="LV")
        result = calc.evaluate(ts)

        assert_frame_equal(result.df, expected.df, check_exact=False, atol=0.01)


class TestWindSpeedHeightCorrection:
    def test_calculation(self) -> None:
        # Taken from FAO56 EXAMPLE 14 https://www.fao.org/4/x0490e/x0490e07.htm#wind%20profile%20relationship
        ts = df_to_ts(pl.DataFrame({"WS": [3.2]}))
        expected = df_to_ts(pl.DataFrame({"WS2m": [2.4]}))

        original_height = 10

        calc = WindSpeedHeightCorrection("WS", original_height, column_name="WS2m")
        result = calc.evaluate(ts)

        assert_frame_equal(result.df, expected.df, check_exact=False, atol=0.01)


class TestActualVapourPressureFao56Eq54:
    def test_calculation(self) -> None:
        # Taken from FAO56 EXAMPLE 19 https://www.fao.org/4/x0490e/x0490e08.htm
        ts = df_to_ts(pl.DataFrame({"RH": [90, 52], "TA": [28, 38]}))
        expected = df_to_ts(pl.DataFrame({"EA": [3.402, 3.445]}))

        calc = ActualVapourPressureFao56Eq54("RH", "TA", column_name="EA")
        result = calc.evaluate(ts)

        assert_frame_equal(result.df, expected.df, check_exact=False, atol=0.001)


class TestVapourPressureCurveSlope:
    def test_calculation(self) -> None:
        # Taken from FAO56 EXAMPLE 18, 19 and 20 https://www.fao.org/4/x0490e/x0490e08.htm
        ts = df_to_ts(pl.DataFrame({"TA": [16.9, 20.7, 28, 38]}))
        expected = df_to_ts(pl.DataFrame({"DELTA": [0.122, 0.15, 0.22, 0.358]}))

        calc = VapourPressureCurveSlope("TA", column_name="DELTA")
        result = calc.evaluate(ts)

        assert_frame_equal(result.df, expected.df, check_exact=False, atol=0.001)


class TestPsychrometricConstant:
    def test_calculation(self) -> None:
        # Taken from FAO56 EXAMPLE 2 https://www.fao.org/4/x0490e/x0490e07.htm#psychrometric%20constant%20(g)
        # Taken from FAO56 EXAMPLE 18 https://www.fao.org/4/x0490e/x0490e08.htm
        ts = df_to_ts(pl.DataFrame({"TA": [16.9, 20], "PA": [100.1, 81.8]}))
        expected = df_to_ts(pl.DataFrame({"GAMMA": [0.00666, 0.0054]}))

        calc = PsychrometricConstant("PA", "TA", column_name="GAMMA")
        result = calc.evaluate(ts)

        assert_frame_equal(result.df, expected.df, check_exact=False, atol=0.001)


class TestSaturationVapourPressure:
    def test_calculation(self) -> None:
        # Taken from FAO56 EXAMPLE 3 https://www.fao.org/4/x0490e/x0490e07.htm
        ts = df_to_ts(pl.DataFrame({"TA": [15.0, 24.5]}))
        expected = df_to_ts(pl.DataFrame({"ES": [1.705, 3.075]}))

        calc = SaturationVapourPressure("TA", column_name="ES")
        result = calc.evaluate(ts)

        assert_frame_equal(result.df, expected.df, check_exact=False, atol=0.001)


class TestPotentialEvapotranspiration30Min:
    def test_calculation(self) -> None:
        # Taken from COSMOS.LEVEL3_DATA_30MIN Oracle DB view:
        #   Site: CHOBH,
        #   Dates: [2015-03-14 04:30:00, 2017-05-30 16:30:00, 2022-01-18 09:30:00, 2023-08-21 11:00:00]

        # Original G data = [-29.6453, 32.23711, -23.7416, 16.64824], for the purposes of this test, it has been
        # duplicated for g1 and g2 values to allow both to be passed in
        ts = df_to_ts(
            pl.DataFrame(
                {
                    "RN": [-68.181, 302.85, 116.2, 364.6],
                    "G1": [-29.6453, 32.23711, -23.7416, 16.64824],
                    "G2": [-29.6453, 32.23711, -23.7416, 16.64824],
                    "TA": [1.977, 19.62, -2.144, 20.54],
                    "RH": [72.5, 57.62, 95.6, 65.41],
                    "WS": [2.89954, 3.204, 0.214, 2.048],
                    "PA": [1024.0, 1011.365, 1033.649, 1020.695],
                }
            )
        )

        # PET results Taken from COSMOS.LEVEL3_DATA_30MIN Oracle DB view
        expected = df_to_ts(pl.DataFrame({"PET": [0.00573, 0.14733, 0.03617, 0.17283]}))

        calc = PotentialEvapotranspiration30Min(
            rn="RN", g1="G1", g2="G2", ta="TA", rh="RH", ws="WS", pa="PA", column_name="PET"
        )
        result = calc.evaluate(ts)

        assert_frame_equal(result.df, expected.df, check_exact=False, atol=0.00001)


class TestNetRadiation:
    def test_calculation(self) -> None:
        ts = df_to_ts(
            pl.DataFrame(
                {
                    "SWIN": [22.9, 19.3, 14, 25.1],
                    "SWOUT": [4.9, 4.2, 3, 5.5],
                    "LWIN": [24.1, 26, 26.2, 23.1],
                    "LWOUT": [31.2, 31.9, 30.9, 30.8],
                }
            )
        )
        expected = df_to_ts(pl.DataFrame({"RN": [10.9, 9.2, 6.3, 11.9]}))

        calc = NetRadiation("SWIN", "SWOUT", "LWIN", "LWOUT", column_name="RN")
        result = calc.evaluate(ts)

        assert_frame_equal(result.df, expected.df, check_exact=False, atol=0.001)


class TestDailyTotalRadiation:
    def test_evaluate(self, ts_test_helper: TimeSeriesTestHelper) -> None:
        df = pl.read_csv(
            ts_test_helper.input_dir.joinpath("derivations", "rn_pt30m_3_days.csv"),
            schema=pl.Schema({"time": pl.Datetime(time_zone=timezone.utc), "SWOUT": pl.Float64}),
        )
        ts = TimeSeries(df, "time", Period.of_iso_duration("PT30M"), Period.of_iso_duration("PT30M"))

        expected = TimeSeries(
            pl.DataFrame(
                {
                    "time": [
                        datetime(2024, 3, 8, 0, 0, 0, tzinfo=timezone.utc),
                        datetime(2024, 3, 9, 0, 0, 0, tzinfo=timezone.utc),
                        datetime(2024, 3, 10, 0, 0, 0, tzinfo=timezone.utc),
                    ],
                    "SWOUT": [727.7881611130434, 593.5016447999999, 382.0865847652174],
                },
                schema=pl.Schema(
                    {
                        "time": pl.Datetime(time_zone=timezone.utc),
                        "SWOUT": pl.Float64,
                    }
                ),
            ),
            "time",
            Period.of_iso_duration("P1D"),
            Period.of_iso_duration("P1D"),
        )

        calc = DailyTotalRadiation(column_name="SWOUT")
        result = calc.evaluate(ts)

        assert_frame_equal(expected.df, result.df)


class TestDailyPotentialEvaporation:
    def test_evaluate(self, ts_test_helper: TimeSeriesTestHelper) -> None:
        df = pl.read_csv(
            ts_test_helper.input_dir.joinpath("derivations", "pe_pt30m_3_days.csv"),
            schema=pl.Schema({"time": pl.Datetime(time_zone=timezone.utc), "PE": pl.Float64}),
        )
        ts = TimeSeries(df, "time", Period.of_iso_duration("PT30M"), Period.of_iso_duration("PT30M"))

        expected = TimeSeries(
            pl.DataFrame(
                {
                    "time": [
                        datetime(2024, 3, 8, 0, 0, 0, tzinfo=timezone.utc),
                        datetime(2024, 3, 9, 0, 0, 0, tzinfo=timezone.utc),
                        datetime(2024, 3, 10, 0, 0, 0, tzinfo=timezone.utc),
                    ],
                    "PE": [80.7080409379832, 71.72157096234429, 57.05958185417873],
                },
                schema=pl.Schema(
                    {
                        "time": pl.Datetime(time_zone=timezone.utc),
                        "PE": pl.Float64,
                    }
                ),
            ),
            "time",
            Period.of_iso_duration("P1D"),
            Period.of_iso_duration("P1D"),
        )

        calc = DailyPotentialEvaporation(pe="PE", column_name="PE")
        result = calc.evaluate(ts)

        assert_frame_equal(expected.df, result.df)
