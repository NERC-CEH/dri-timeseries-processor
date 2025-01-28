import unittest
import polars as pl
import numpy as np
from datetime import datetime
from polars.testing import assert_frame_equal

from dritimeseriesprocessor.infilling.methods import linear_interpolation

from time_series import TimeSeries, Period


class TestLinearInterpolation(unittest.TestCase):
    """
    A test case for the linear_interpolation function.
    """
    def setUp(self):
        """
        Set up common test data and mocks.
        """
        data = pl.DataFrame({
            'time': [
                datetime(2023, 8, 10),
                datetime(2023, 8, 11),
                datetime(2023, 8, 12),
                datetime(2023, 8, 13),
                datetime(2023, 8, 14),
                datetime(2023, 8, 15),
                datetime(2023, 8, 16),
            ],
            'temperature': [20.0, np.nan, 22.0, np.nan, 21.0, 20.0, 19.0],
            'humidity': [50, 54, None, None, 60, None, 70]
        })

        resolution = Period.of_days(1)
        periodicity = Period.of_days(1)
        self.ts = TimeSeries(
            data,
            "time",
            resolution,
            periodicity
        )

        self.ts.add_flag_system("infill_flags", {
            "INTERP_LINEAR": 1
        })
        self.ts.init_flag_column("infill_flags", "temperature_INFILL_FLAG")
        self.ts.init_flag_column("infill_flags", "humidity_INFILL_FLAG")


    def test_basic_interpolation(self):
        """
        Test basic linear interpolation without a max_gap_size.
        """
        # Gaps given as NaNs
        result = linear_interpolation(self.ts, "temperature", "temperature_INFILL_FLAG")
        self.assertEqual(result.df['temperature'].to_list(), [20.0, 21.0, 22.0, 21.5, 21.0, 20.0, 19.0])
        self.assertEqual(result.df['temperature_INFILL_FLAG'].to_list(), [0, 1, 0, 1, 0, 0, 0])

        # Gaps given as None
        result = linear_interpolation(self.ts, "humidity", "humidity_INFILL_FLAG")
        self.assertEqual(result.df['humidity'].to_list(), [50, 54, 56, 58, 60, 65, 70])
        self.assertEqual(result.df['humidity_INFILL_FLAG'].to_list(), [0, 0, 1, 1, 0, 1, 0])

    def test_max_gap_size(self):
        """
        Test interpolation with a specified max_gap_size.
        """
        result = linear_interpolation(self.ts, "humidity", "humidity_INFILL_FLAG", max_gap_size=1)
        self.assertEqual(result.df['humidity'].to_list(), [50, 54, None, None, 60, 65, 70])
        self.assertEqual(result.df['humidity_INFILL_FLAG'].to_list(), [0, 0, 0, 0, 0, 1, 0])

    def test_no_nulls(self):
        """
        Test the function with a series containing no null values makes no changes.
        """
        self.ts.df = self.ts.df = self.ts.df.with_columns(pl.Series("no_null", [20.0, 21.0, 22.0, 21.5, 21.0, 20.0, 19.0]))
        self.ts.init_flag_column("infill_flags", "no_null_INFILL_FLAG")

        result = linear_interpolation(self.ts, "no_null", "no_null_INFILL_FLAG")
        assert_frame_equal(result.df, self.ts.df)

    def test_all_nulls(self):
        """
        Test the function with a series containing only null values makes no changes.
        """
        self.ts.df = self.ts.df.with_columns(pl.Series("all_null", [None] * 7, dtype=pl.Float64))
        self.ts.init_flag_column("infill_flags", "all_null_INFILL_FLAG")

        result = linear_interpolation(self.ts, "all_null", "all_null_INFILL_FLAG")
        assert_frame_equal(result.df, self.ts.df)

    def test_edge_cases(self):
        """
        Test edge cases: nulls at the beginning and end of the series should not be infilled
        """
        self.ts.df = self.ts.df.with_columns(pl.Series("end_nulls", [None, 21.0, 22.0, None, 21.0, 20.0, None]))
        self.ts.init_flag_column("infill_flags", "end_nulls_INFILL_FLAG")

        result = linear_interpolation(self.ts, "end_nulls", "end_nulls_INFILL_FLAG")
        self.assertEqual(result.df['end_nulls'].to_list(), [None, 21.0, 22.0, 21.5, 21.0, 20.0, None])
        self.assertEqual(result.df['end_nulls_INFILL_FLAG'].to_list(), [0, 0, 0, 1, 0, 0, 0])

if __name__ == '__main__':
    unittest.main()