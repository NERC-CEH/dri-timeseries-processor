from datetime import datetime, timezone
import unittest

import polars as pl
from polars.testing import assert_frame_equal

from time_stream import Period, TimeSeries
from dritimeseriesprocessor.deriving.calculation import Calculation
from dritimeseriesprocessor.deriving.derivations import (
    derive,
    ActualVapourPressureFao56Eq54,
    LatentHeatOfVaporization,
    PotentialEvapotranspiration30Min,
    PsychrometricConstant,
    SaturationVapourPressure,
    VapourPressureCurveSlope,
    WindSpeedHeightCorrection,
)
from dritimeseriesprocessor.deriving.unit_conversions import HpaToKpa, WattsToMegajoules


TZ_UTC = timezone.utc


def init_timeseries():
    df = pl.DataFrame({
        "time": [datetime(2024, 1, 1), datetime(2024, 1, 2), datetime(2024, 1, 3)],
        "data_col1": [1, 2, 3],
        "data_col2": [4, 5, 6]
    })
    ts = TimeSeries(df, "time")
    return ts

class MockCalculation(Calculation):
    # Zero dependencies
    def __init__(self, column_name):
        super().__init__("Mock calculation", column_name, "mock_unit")

    @property
    def default_column_name(self) -> str:
        return "mock_calc"

    def expr(self) -> pl.Expr:
        return pl.lit(42)


class TestDerive(unittest.TestCase):
    def test_derive_calculation(self):
        """ Test that a new timeseries is created when deriving a calculation, with appropriate metadata and data. """
        ts = init_timeseries()
        calc = MockCalculation
        result = derive(ts, calc)

        expected_df = pl.DataFrame({
            "time": [
                datetime(2024, 1, 1, tzinfo=TZ_UTC),
                datetime(2024, 1, 2, tzinfo=TZ_UTC),
                datetime(2024, 1, 3, tzinfo=TZ_UTC)
            ],
            "data_col1": [1, 2, 3],
            "data_col2": [4, 5, 6],
            "mock_calc": [42, 42, 42],
        })

        self.assertIn("mock_calc", result.data_columns)
        self.assertEqual(result.mock_calc.metadata(), {"units": "mock_unit"})
        assert_frame_equal(result.df, expected_df, check_dtype=False)


class TestLatentHeatOfVaporization(unittest.TestCase):
    def test_calculation(self):
        df = pl.DataFrame({"TA": [-20, 0, 20, 100]})
        expected = df.with_columns(pl.Series("LV", [2.54, 2.501, 2.45, 2.26]))

        calc = LatentHeatOfVaporization("TA", column_name="LV")
        result = calc.evaluate(df)

        assert_frame_equal(result, expected, check_exact=False, atol=0.01)


class TestWindSpeedHeightCorrection(unittest.TestCase):
    def test_calculation(self):
        # Taken from FAO56 EXAMPLE 14 https://www.fao.org/4/x0490e/x0490e07.htm#wind%20profile%20relationship
        df = pl.DataFrame({"WS": [3.2]})
        original_height = 10
        expected = df.with_columns(pl.Series("WS2m", [2.4]))

        calc = WindSpeedHeightCorrection("WS", original_height, column_name="WS2m")
        result = calc.evaluate(df)

        assert_frame_equal(result, expected, check_exact=False, atol=0.01)


class TestActualVapourPressureFao56Eq54(unittest.TestCase):
    def test_calculation(self):
        # Taken from FAO56 EXAMPLE 19 https://www.fao.org/4/x0490e/x0490e08.htm
        df = pl.DataFrame({"RH": [90, 52], "TA": [28, 38]})
        expected = df.with_columns(pl.Series("EA", [3.402, 3.445]))

        calc = ActualVapourPressureFao56Eq54("RH", "TA", column_name="EA")
        result = calc.evaluate(df)

        assert_frame_equal(result, expected, check_exact=False, atol=0.001)


class TestVapourPressureCurveSlope(unittest.TestCase):
    def test_calculation(self):
        # Taken from FAO56 EXAMPLE 18, 19 and 20 https://www.fao.org/4/x0490e/x0490e08.htm
        df = pl.DataFrame({"TA": [16.9, 20.7, 28, 38]})
        expected = df.with_columns(pl.Series("DELTA", [0.122, 0.15, 0.22, 0.358]))

        calc = VapourPressureCurveSlope("TA", column_name="DELTA")
        result = calc.evaluate(df)

        assert_frame_equal(result, expected, check_exact=False, atol=0.001)


class TestPsychrometricConstant(unittest.TestCase):
    def test_calculation(self):
        # Taken from FAO56 EXAMPLE 2 https://www.fao.org/4/x0490e/x0490e07.htm#psychrometric%20constant%20(g)
        # Taken from FAO56 EXAMPLE 18 https://www.fao.org/4/x0490e/x0490e08.htm
        df = pl.DataFrame({"TA": [16.9, 20], "PA": [100.1, 81.8]})
        expected = df.with_columns(pl.Series("GAMMA", [0.0666, 0.054]))

        calc = PsychrometricConstant("PA", "TA", column_name="GAMMA")
        result = calc.evaluate(df)

        assert_frame_equal(result, expected, check_exact=False, atol=0.001)


class TestSaturationVapourPressure(unittest.TestCase):
    def test_calculation(self):
        # Taken from FAO56 EXAMPLE 3 https://www.fao.org/4/x0490e/x0490e07.htm
        df = pl.DataFrame({"TA": [15., 24.5]})
        expected = df.with_columns(pl.Series("ES", [1.705, 3.075]))

        calc = SaturationVapourPressure("TA", column_name="ES")
        result = calc.evaluate(df)

        assert_frame_equal(result, expected, check_exact=False, atol=0.001)


class TestPotentialEvapotranspiration30Min(unittest.TestCase):
    def test_calculation(self):
        # Taken from COSMOS.LEVEL3_DATA_30MIN Oracle DB view:
        #   Site: CHOBH,
        #   Dates: [2015-03-14 04:30:00, 2017-05-30 16:30:00, 2022-01-18 09:30:00, 2023-08-21 11:00:00]
        df = pl.DataFrame({
            "RN": [-68.181, 302.85, 116.2, 364.6],
            "G": [-29.6453, 32.23711, -23.7416, 16.64824],
            "TA": [1.977, 19.62, -2.144, 20.54],
            "RH": [72.5, 57.62, 95.6, 65.41],
            "WS": [2.89954, 3.204, 0.214, 2.048],
            "PA": [1024., 1011.365, 1033.649, 1020.695],
        })

        period = Period.of_minutes(30)
        original_ws_height = 2.6

        df = HpaToKpa("PA").evaluate(df, allow_override=True)
        df = WattsToMegajoules("RN", period, "RN_MJ").evaluate(df, allow_override=True)
        df = WattsToMegajoules("G", period, "G_MJ").evaluate(df, allow_override=True)
        df = WindSpeedHeightCorrection("WS", original_ws_height, column_name="WS2m").evaluate(df)

        # PET results Taken from COSMOS.LEVEL3_DATA_30MIN Oracle DB view
        expected = df.with_columns(pl.Series("PET", [0.00573, 0.14733, 0.03617, 0.17283]))

        calc = PotentialEvapotranspiration30Min("RN_MJ", "G_MJ", "TA", "RH", "WS2m", "PA", column_name="PET")
        result = calc.evaluate(df)

        assert_frame_equal(result, expected, check_exact=False, atol=0.00001)
