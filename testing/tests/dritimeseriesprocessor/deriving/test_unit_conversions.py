from datetime import datetime

import polars as pl
from polars.testing import assert_frame_equal
from time_stream import Period, TimeSeries

from dritimeseriesprocessor.deriving.unit_conversions import HpaToKpa, WattsToMegajoules


class TestHpaToKpa:
    period = Period.of_minutes(1)

    def test_hpa_to_kpa(self) -> None:
        """Test that hpa to kpa conversion works as expected."""
        df = pl.DataFrame(
            {
                "time": [
                    datetime(2023, 1, 1, 0, 0),
                    datetime(2023, 1, 1, 0, 1),
                    datetime(2023, 1, 1, 0, 2),
                ],
                "Col1": [1000.0, 0.0, 1234.56],
            }
        )
        ts = TimeSeries(df, time_name="time", resolution=self.period, periodicity=self.period)
        conversion = HpaToKpa("Col1", "Col1_kPa")
        result = conversion.evaluate(ts)

        expected = pl.DataFrame(
            {
                "time": [
                    datetime(2023, 1, 1, 0, 0),
                    datetime(2023, 1, 1, 0, 1),
                    datetime(2023, 1, 1, 0, 2),
                ],
                "Col1_kPa": [100.0, 0, 123.456],
            }
        )

        assert_frame_equal(result.df, expected)
        assert conversion.units == "kPa"


class TestWattsToMegajoules:
    period = Period.of_minutes(60)

    def test_w_to_mj(self) -> None:
        """Test that watts to megajoules conversion works as expected."""
        df = pl.DataFrame(
            {
                "time": [
                    datetime(2023, 1, 1, 0, 0),
                    datetime(2023, 1, 1, 1, 0),
                    datetime(2023, 1, 1, 2, 0),
                    datetime(2023, 1, 1, 3, 0),
                    datetime(2023, 1, 1, 4, 0),
                ],
                "Col1": [-100.0, -25.9, 0.0, 25.9, 100.0],
            }
        )
        ts = TimeSeries(df, time_name="time", resolution=self.period, periodicity=self.period)
        conversion = WattsToMegajoules("Col1", self.period, "Col1_mj")
        result = conversion.evaluate(ts)

        expected = pl.DataFrame(
            {
                "time": [
                    datetime(2023, 1, 1, 0, 0),
                    datetime(2023, 1, 1, 1, 0),
                    datetime(2023, 1, 1, 2, 0),
                    datetime(2023, 1, 1, 3, 0),
                    datetime(2023, 1, 1, 4, 0),
                ],
                "Col1_mj": [-0.36, -0.09324, 0.0, 0.09324, 0.36],
            }
        )

        assert_frame_equal(result.df, expected)
        assert conversion.units == "MJ"
