import unittest
from unittest.mock import patch

import polars as pl
from polars.testing import assert_frame_equal

from time_series import Period
from dritimeseriesprocessor.deriving.unit_conversions import Conversion, HpaToKpa, WattsToMegajoules


# Override the abstract methods to allow class instantiation
@patch.object(Conversion, '__abstractmethods__', set())
@patch.object(Conversion, '_expr', lambda self: "expr")
@patch.object(Conversion, '_rexpr', lambda self: "rexpr")
class TestDetermineConversion(unittest.TestCase):
    def test_no_reverse_units(self):
        """ Test that the from and to units are maintained when no reverse is specified."""
        conversion = Conversion("Col1", "Test Conversion", "Units_A", "Units_B", reverse=False)
        result = conversion._determine_conversion("Units_A", "Units_B")
        expected = ("Units_A", "Units_B")
        self.assertEqual(result, expected)
        self.assertEqual(conversion.units, "Units_B")

    def test_reverse_units(self):
        """ Test that the from and to units are flipped when reverse is specified."""
        conversion = Conversion("Col1", "Test Conversion", "Units_A", "Units_B", reverse=True)
        result = conversion._determine_conversion("Units_A", "Units_B")
        expected = ("Units_B", "Units_A")
        self.assertEqual(result, expected)
        self.assertEqual(conversion.units, "Units_A")

    def test_no_reverse_expr(self):
        """ Test that the correct expr is returned no reverse is specified."""
        conversion = Conversion("Col1", "Test Conversion", "Units_A", "Units_B", reverse=False)
        result = conversion.expr()
        expected = conversion._expr()
        self.assertEqual(result, expected)

    def test_reverse_expr(self):
        """ Test that the correct expr is returned no reverse is specified."""
        conversion = Conversion("Col1", "Test Conversion", "Units_A", "Units_B", reverse=True)
        result = conversion.expr()
        expected = conversion._rexpr()
        self.assertEqual(result, expected)


class TestHpaToKpa(unittest.TestCase):
    def test_hpa_to_kpa(self):
        """ Test that hpa to kpa conversion works as expected."""
        df = pl.DataFrame({"Col1": [1000., 0., 1234.56]})
        conversion = HpaToKpa("Col1", "Col1_kPa")
        result = conversion.evaluate(df)

        expected = df.with_columns(pl.Series("Col1_kPa", [100., 0, 123.456]))
        assert_frame_equal(result, expected)
        self.assertEqual(conversion.units, "kPa")

    def test_kpa_to_hpa(self):
        """ Test that kpa to hpa conversion works as expected."""
        df = pl.DataFrame({"Col1": [100., 0, 123.456]})
        conversion = HpaToKpa("Col1", "Col1_hPa", reverse=True)
        result = conversion.evaluate(df)

        expected = df.with_columns(pl.Series("Col1_hPa", [1000., 0., 1234.56]))
        assert_frame_equal(result, expected)
        self.assertEqual(conversion.units, "hPa")


class TestWattsToMegajoules(unittest.TestCase):
    period = Period.of_minutes(60)

    def test_w_to_mj(self):
        """ Test that watts to megajoules conversion works as expected."""
        df = pl.DataFrame({"Col1": [-100., -25.9, 0., 25.9, 100.]})
        conversion = WattsToMegajoules("Col1", self.period, "Col1_mj")
        result = conversion.evaluate(df)

        expected = df.with_columns(pl.Series("Col1_mj", [-0.36, -0.09324, 0.0, 0.09324, 0.36]))
        assert_frame_equal(result, expected)
        self.assertEqual(conversion.units, "MJ")

    def test_mj_to_w(self):
        """ Test that megajoules to watts conversion works as expected."""
        df = pl.DataFrame({"Col1": [-0.36, -0.09324, 0.0, 0.09324, 0.36]})
        conversion = WattsToMegajoules("Col1", self.period, "Col1_w", reverse=True)
        result = conversion.evaluate(df)

        expected = df.with_columns(pl.Series("Col1_w", [-100., -25.9, 0., 25.9, 100.]))
        assert_frame_equal(result, expected)
        self.assertEqual(conversion.units, "W")