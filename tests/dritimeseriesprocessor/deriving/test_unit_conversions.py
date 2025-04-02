import unittest

import polars as pl
from polars.testing import assert_frame_equal

from time_stream import Period
from dritimeseriesprocessor.deriving.unit_conversions import HpaToKpa, WattsToMegajoules


class TestHpaToKpa(unittest.TestCase):
    def test_hpa_to_kpa(self):
        """ Test that hpa to kpa conversion works as expected."""
        df = pl.DataFrame({"Col1": [1000., 0., 1234.56]})
        conversion = HpaToKpa("Col1", "Col1_kPa")
        result = conversion.evaluate(df)

        expected = df.with_columns(pl.Series("Col1_kPa", [100., 0, 123.456]))
        assert_frame_equal(result, expected)
        self.assertEqual(conversion.units, "kPa")


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
