import unittest
from unittest.mock import Mock
from parameterized import parameterized

import polars as pl
from time_stream import TimeSeries
from polars.testing import assert_frame_equal
from datetime import datetime

from dritimeseriesprocessor.correcting.operations import Operation, Add, Multiply, Power, LWCorrection


def create_test_ts(data=[1., 2., 3., 4., 5., 6., 7.]) -> TimeSeries:
    """Set up test fixtures."""
    df = pl.DataFrame({
        "timestamp": [datetime(2025, m, 1) for m in range(1, 8)],
        "value": data,
    })

    return TimeSeries(df, "timestamp", metadata={"column_name": "value"})


def create_test_filter() -> pl.Expr:
    """Set up a date filter for tests."""
    start_date = datetime(2025, 3, 1)
    end_date = datetime(2025, 5, 1)
    time_name = "timestamp"
    return pl.col(time_name).is_between(start_date, end_date)



class TestOperation(unittest.TestCase):
    @parameterized.expand([
        ("add", {"correction_factor": 10}, Add),
        ("multiply", {"correction_factor": 2}, Multiply),
    ])
    def test_get_with_string(self, get_input, input_args, expected):
        """Test Operation.get() with string input."""
        op = Operation.get(get_input, **input_args)
        self.assertIsInstance(op, expected)
        for arg, val in input_args.items():
            self.assertEqual(getattr(op, arg), val)

    def test_get_with_bad_string(self):
        """Test Operation.get() with invalid string."""
        with self.assertRaises(ValueError):
            Operation.get("bad_operation")


class TestAdd(unittest.TestCase):
    def setUp(self):
        self.ts = create_test_ts()
        self.date_filter = create_test_filter()

    @parameterized.expand([
        (100, [101., 102., 103., 104., 105., 106., 107.]),
        (0, [1., 2., 3., 4., 5., 6., 7.]),
        (-1, [0., 1., 2., 3., 4., 5., 6.]),
    ])
    def test_add_simple(self, factor, expected):
        """ Test that the add function works across the full DataFrame
        """
        adder = Add(factor)
        result = adder.apply(self.ts)
        expected_df = pl.DataFrame({
            "timestamp": [datetime(2025, m, 1) for m in range(1, 8)],
            "value": expected,
        })
        assert_frame_equal(result.df, expected_df)

    @parameterized.expand([
        (100, [1., 2., 103., 104., 105., 6., 7.]),
        (0, [1., 2., 3., 4., 5., 6., 7.]),
        (-1, [1., 2., 2., 3., 4., 6., 7.]),
    ])
    def test_date_filter(self, factor, expected):
        """ Test that the add function works with a mask clause
        """
        adder = Add(factor)
        result = adder.apply(self.ts, filter_expr=self.date_filter)
        expected_df = pl.DataFrame({
            "timestamp": [datetime(2025, m, 1) for m in range(1, 8)],
            "value": expected,
        })
        assert_frame_equal(result.df, expected_df)


class TestMultiply(unittest.TestCase):
    def setUp(self):
        self.ts = create_test_ts()
        self.date_filter = create_test_filter()

    @parameterized.expand([
        (2, [2., 4., 6., 8., 10., 12., 14.]),
        (1, [1., 2., 3., 4., 5., 6., 7.]),
        (0, [0., 0., 0., 0., 0., 0., 0.]),
        (-1, [-1., -2., -3., -4., -5., -6., -7.]),
        (0.5, [0.5, 1., 1.5, 2., 2.5, 3., 3.5]),
    ])
    def test_multiply_simple(self, factor, expected):
        """ Test that the Multiply function works across the full DataFrame
        """
        multiplier = Multiply(factor)
        result = multiplier.apply(self.ts)
        expected_df = pl.DataFrame({
            "timestamp": [datetime(2025, m, 1) for m in range(1, 8)],
            "value": expected,
        })
        assert_frame_equal(result.df, expected_df)

    @parameterized.expand([
        (2, [1., 2., 6., 8., 10., 6., 7.]),
        (1, [1., 2., 3., 4., 5., 6., 7.]),
        (0, [1., 2., 0., 0., 0., 6., 7.]),
    ])
    def test_date_filter(self, factor, expected):
        """ Test that the Multiply function works with a mask clause
        """
        multiplier = Multiply(factor)
        result = multiplier.apply(self.ts, filter_expr=self.date_filter)
        expected_df = pl.DataFrame({
            "timestamp": [datetime(2025, m, 1) for m in range(1, 8)],
            "value": expected,
        })
        assert_frame_equal(result.df, expected_df)


class TestPower(unittest.TestCase):
    def setUp(self):
        self.ts = create_test_ts()
        self.date_filter = create_test_filter()

    @parameterized.expand([
        (2, [1., 4., 9., 16., 25., 36., 49.]),
        (3, [1., 8., 27., 64., 125., 216., 343.]),
        (1, [1., 2., 3., 4., 5., 6., 7.]),
        (0, [1., 1., 1., 1., 1., 1., 1.]),
    ])
    def test_power_simple(self, factor, expected):
        """ Test that the Power function works across the full DataFrame
        """
        power_op = Power(factor)
        result = power_op.apply(self.ts)
        expected_df = pl.DataFrame({
            "timestamp": [datetime(2025, m, 1) for m in range(1, 8)],
            "value": expected,
        })
        assert_frame_equal(result.df, expected_df)

    @parameterized.expand([
        (2, [1., 2., 9., 16., 25., 6., 7.]),
        (3, [1., 2., 27., 64., 125., 6., 7.]),
        (1, [1., 2., 3., 4., 5., 6., 7.]),
        (0, [1., 2., 1., 1., 1., 6., 7.]),
    ])
    def test_date_filter(self, factor, expected):
        """ Test that the Power function works with a mask clause
        """
        power_op = Power(factor)
        result = power_op.apply(self.ts, filter_expr=self.date_filter)
        expected_df = pl.DataFrame({
            "timestamp": [datetime(2025, m, 1) for m in range(1, 8)],
            "value": expected,
        })
        assert_frame_equal(result.df, expected_df)


class TestLWCorrection(unittest.TestCase):
    def setUp(self):
        self.lw = create_test_ts([373.9, 381.5, 386.9, 398.9, 387.7, 387.3, 391.8])
        self.lw_unc = create_test_ts([-53.24, -56.31, -56.64, -41.11, -64.04, -75.39, -81.5])
        self.ta = create_test_ts([20.33, 21.74, 22.79, 22.91, 24.3, 25.72, 27.27])
        self.factor = 1.00924
        self.date_filter = create_test_filter()

    def test_lw_correction_simple(self):
        """ Test that the LWCorrection function works across the full DataFrame
        """
        lw_correction = LWCorrection(self.lw_unc, self.ta, self.factor)
        result = lw_correction.apply(self.lw)
        expected_df = pl.DataFrame({
            "timestamp": [datetime(2025, m, 1) for m in range(1, 8)],
            "value": [366.9, 371.9, 377.7, 394.1, 379.2, 376.3, 379.6],
        })
        assert_frame_equal(result.df, expected_df)

    def test_date_filter(self):
        """ Test that the LWCorrection function works with a mask clause
        """
        lw_correction = LWCorrection(self.lw_unc, self.ta, self.factor)
        result = lw_correction.apply(self.lw, filter_expr=self.date_filter)
        expected_df = pl.DataFrame({
            "timestamp": [datetime(2025, m, 1) for m in range(1, 8)],
            "value": [373.9, 381.5, 377.7, 394.1, 379.2, 387.3, 391.8],
        })
        assert_frame_equal(result.df, expected_df)
