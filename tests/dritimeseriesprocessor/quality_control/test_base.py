import unittest
from datetime import datetime

import polars as pl
from polars.testing import assert_series_equal

from time_stream import TimeSeries, Period
from dritimeseriesprocessor.quality_control.base import BaseCheck, DepTS


class DummyCheck(BaseCheck):
    def __init__(self, qc_column: str, flag_column: str, flag_name: str) -> None:
        super().__init__(qc_column=qc_column, flag_column=flag_column, flag_name=flag_name)

    def _check_expression(self, ts: TimeSeries, dep_ts: DepTS = None) -> pl.Expr:
        return pl.lit(True)


class TestGetThresholdExpression(unittest.TestCase):
    def setUp(self):
        times = [datetime(2023, 8, 10), datetime(2023, 8, 11), datetime(2023, 8, 12), datetime(2023, 8, 13)]
        data = pl.DataFrame({
            "time": times,
            "value_a": [5., 10., 20., 30.],
            "value_b": [1.0, 1.1, 1.2, 1.3],
            "value_c": [None, 50., 100., None]
        })

        resolution = Period.of_days(1)
        periodicity = Period.of_days(1)

        self.ts = TimeSeries(data, "time", resolution, periodicity)
        self.check = DummyCheck("", "", "")

    def test_greater_than(self):
        """ Test the column threshold check function with '>' operator.
        """
        result = self.check.get_threshold_expression(self.ts, "value_a", 10, ">")
        expected = pl.Series("value_a", [False, False, True, True])
        assert_series_equal(self.ts.df.select(result)["value_a"], expected)


    def test_greater_than_or_equal(self):
        """ Test the column threshold check function with '>=' operator.
        """
        result = self.check.get_threshold_expression(self.ts, "value_a", 10, ">=")
        expected = pl.Series("value_a", [False, True, True, True])
        assert_series_equal(self.ts.df.select(result)["value_a"], expected)

    def test_less_than(self):
        """ Test the column threshold check function with '<' operator.
        """
        result = self.check.get_threshold_expression(self.ts, "value_a", 10, "<")
        expected = pl.Series("value_a", [True, False, False, False])
        assert_series_equal(self.ts.df.select(result)["value_a"], expected)

    def test_less_than_or_equal(self):
        """ Test the column threshold check function with '<=' operator.
        """
        result = self.check.get_threshold_expression(self.ts, "value_a", 10, "<=")
        expected = pl.Series("value_a", [True, True, False, False])
        assert_series_equal(self.ts.df.select(result)["value_a"], expected)

    def test_equal(self):
        """ Test the column threshold check function with '==' operator.
        """
        result = self.check.get_threshold_expression(self.ts, "value_a", 10, "==")
        expected = pl.Series("value_a", [False, True, False, False])
        assert_series_equal(self.ts.df.select(result)["value_a"], expected)

    def test_not_equal(self):
        """ Test the column threshold check function with '!=' operator.
        """
        result = self.check.get_threshold_expression(self.ts, "value_a", 10, "!=")
        expected = pl.Series("value_a", [True, False, True, True])
        assert_series_equal(self.ts.df.select(result)["value_a"], expected)

    def test_flag_na_when_true(self):
        """ Test that setting flag_na to True means that any NULL values in the check column are treated as failing
        the QC check (so qc flag set in result)
        """
        result = self.check.get_threshold_expression(self.ts, "value_c", 10, ">", flag_na=True)
        expected = pl.Series("value_c", [True, True, True, True])
        assert_series_equal(self.ts.df.select(result)["value_c"], expected)

    def test_flag_na_when_false(self):
        """ Test that setting flag_na to False means that any NULL values in the check column are ignored in
        the QC check (so qc flag not set in result)
        """
        result = self.check.get_threshold_expression(self.ts, "value_c", 10, ">", flag_na=False)
        expected = pl.Series("value_c", [None, True, True, None])
        assert_series_equal(self.ts.df.select(result)["value_c"], expected)

    def test_invalid_operator(self):
        """ Test that invalid operator raises error
        """
        with self.assertRaises(KeyError):
            self.check.get_threshold_expression(self.ts, "value_c", 10, ">>")
