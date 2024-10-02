import unittest
import polars as pl
from polars.testing import assert_frame_equal

from dritimeseriesprocessor.infilling.methods import linear_interpolation


class TestLinearInterpolation(unittest.TestCase):
    """
    A test case for the linear_interpolation function.
    """

    def test_basic_interpolation(self):
        """
        Test basic linear interpolation without a max_gap_size.
        """
        data = pl.Series([1.0, None, 3.0, None, 5.0])
        result = linear_interpolation(data)

        expected = pl.DataFrame({
            'value': [1.0, None, 3.0, None, 5.0],
            'value_filled': [None, 2.0, None, 4.0, None],
            'method_id': [None, 'INTERP_LINEAR', None, 'INTERP_LINEAR', None]
        })

        assert_frame_equal(result, expected)

    def test_max_gap_size(self):
        """
        Test interpolation with a specified max_gap_size.
        """
        data = pl.Series([1.0, None, None, None, 5.0, None, 7.0])
        result = linear_interpolation(data, max_gap_size=2)

        expected = pl.DataFrame({
            'value': [1.0, None, None, None, 5.0, None, 7.0],
            'value_filled': [None, None, None, None, None, 6.0, None],
            'method_id': [None, None, None, None, None, 'INTERP_LINEAR', None]
        })

        assert_frame_equal(result, expected)

    def test_no_nulls(self):
        """
        Test the function with a series containing no null values.
        """
        data = pl.Series([1.0, 2.0, 3.0, 4.0, 5.0])
        result = linear_interpolation(data)

        expected = pl.DataFrame({
            'value': [1.0, 2.0, 3.0, 4.0, 5.0],
            'value_filled': [None, None, None, None, None],
            'method_id': [None, None, None, None, None]
        }, schema={
            "value": pl.Float64,
            "value_filled": pl.Float64,
            "method_id": str
        })
        assert_frame_equal(result, expected)

    def test_all_nulls(self):
        """
        Test the function with a series containing only null values.
        """
        data = pl.Series([None, None, None], dtype=pl.Float64)
        result = linear_interpolation(data)

        expected = pl.DataFrame({
            'value': [None, None, None],
            'value_filled': [None, None, None],
            'method_id': [None, None, None]
        }, schema={
            "value": pl.Float64,
            "value_filled": pl.Float64,
            "method_id": str
        })
        assert_frame_equal(result, expected)

    def test_edge_cases(self):
        """
        Test edge cases: nulls at the beginning and end of the series.
        """
        data = pl.Series([None, 2.0, None, 4.0, None])
        result = linear_interpolation(data)

        expected = pl.DataFrame({
            'value': [None, 2.0, None, 4.0, None],
            'value_filled': [None, None, 3.0, None, None],
            'method_id': [None, None, 'INTERP_LINEAR', None, None]
        })

        assert_frame_equal(result, expected)
