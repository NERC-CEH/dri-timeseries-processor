import unittest
from unittest.mock import Mock

import polars as pl
from polars.testing import assert_frame_equal

from dritimeseriesprocessor.preprocessing.operations import add, multiply, power


def create_test_data():
    return pl.DataFrame({
        "SITE_ID": ["site1", "site2", "site3"],
        "value": [10., 20., 30.],
    })


class TestAdd(unittest.TestCase):
    def setUp(self):
        self.df = create_test_data()

    def test_add_simple(self):
        """ Test that the add function works across the full DataFrame
        """
        result = add(self.df, "value", 100)
        expected = pl.DataFrame({
            "SITE_ID": ["site1", "site2", "site3"],
            "value": [110., 120., 130.],
        })

        assert_frame_equal(result, expected)

    def test_add_mask(self):
        """ Test that the add function works with a mask clause
        """
        mask = pl.col("SITE_ID").eq("site1")
        result = add(self.df, "value", 100, mask)
        expected = pl.DataFrame({
            "SITE_ID": ["site1", "site2", "site3"],
            "value": [110., 20., 30.],
        })

        assert_frame_equal(result, expected)

    def test_no_matching_rows(self):
        """ Test when no rows match the condition
        """
        mask = pl.col("SITE_ID").eq("site4")
        result = add(self.df, "value", 100, mask)
        assert_frame_equal(result, self.df)


class TestMultiply(unittest.TestCase):
    def setUp(self):
        self.df = create_test_data()

    def test_multiply_simple(self):
        """ Test that the multiply function works across the full DataFrame
        """
        result = multiply(self.df, "value", 2.)
        expected = pl.DataFrame({
            "SITE_ID": ["site1", "site2", "site3"],
            "value": [20., 40., 60.],
        })

        assert_frame_equal(result, expected)

    def test_multiply_mask(self):
        """ Test that the multiply function works with a mask clause
        """
        mask = pl.col("SITE_ID").eq("site2")
        result = multiply(self.df, "value", 2., mask)
        expected = pl.DataFrame({
            "SITE_ID": ["site1", "site2", "site3"],
            "value": [10., 40., 30.],
        })

        assert_frame_equal(result, expected)

    def test_no_matching_rows(self):
        """ Test there is no change when no rows match the mask expression
        """
        mask = pl.col("SITE_ID").eq("site4")
        result = multiply(self.df, "value", 2., mask)
        assert_frame_equal(result, self.df)


class TestPower(unittest.TestCase):
    def setUp(self):
        self.df = create_test_data()

    def test_power_simple(self):
        """ Test that the power function works across the full DataFrame
        """
        result = power(self.df, "value", 2.)
        expected = pl.DataFrame({
            "SITE_ID": ["site1", "site2", "site3"],
            "value": [100., 400., 900.],
        })

        assert_frame_equal(result, expected)

    def test_power_mask(self):
        """ Test that the power function works with a mask clause
        """
        mask = pl.col("SITE_ID").eq("site2")
        result = power(self.df, "value", 2., mask)
        expected = pl.DataFrame({
            "SITE_ID": ["site1", "site2", "site3"],
            "value": [10., 400., 30.],
        })

        assert_frame_equal(result, expected)

    def test_no_matching_rows(self):
        """ Test there is no change when no rows match the mask expression
        """
        mask = pl.col("SITE_ID").eq("site4")
        result = power(self.df, "value", 2., mask)
        assert_frame_equal(result, self.df)
