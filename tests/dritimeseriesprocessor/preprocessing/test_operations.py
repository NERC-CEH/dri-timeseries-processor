import unittest
from unittest.mock import Mock

import polars as pl
from polars.testing import assert_frame_equal

from dritimeseriesprocessor.preprocessing.operations import add, multiply, power


def create_test_data():
    return pl.DataFrame({
        "SITE_ID": ["site1", "site2", "site3"],
        "value": [10., 20., 30.],
        "value_PRFLAG": [None, None, None],
    }).with_columns(pl.col("value_PRFLAG").cast(pl.Utf8))


class TestAdd(unittest.TestCase):
    def setUp(self):
        self.df = create_test_data()
        self.correction_config = Mock(
            VARIABLE="value",
            CORRECTION_FACTOR=100.,
            METHOD_ID="ADD",
        )

    def test_add_simple(self):
        """ Test that the add function works across the full DataFrame
        """
        result = add(self.df, self.correction_config, "value_PRFLAG")
        expected = pl.DataFrame({
            "SITE_ID": ["site1", "site2", "site3"],
            "value": [110., 120., 130.],
            "value_PRFLAG": ["ADD", "ADD", "ADD"],
        })

        assert_frame_equal(result, expected)

    def test_add_mask(self):
        """ Test that the add function works with a mask clause
        """
        mask = pl.col("SITE_ID").eq("site1")
        result = add(self.df, self.correction_config, "value_PRFLAG", mask)
        expected = pl.DataFrame({
            "SITE_ID": ["site1", "site2", "site3"],
            "value": [110., 20., 30.],
            "value_PRFLAG": ["ADD", None, None],
        })

        assert_frame_equal(result, expected)

    def test_no_matching_rows(self):
        """ Test when no rows match the condition
        """
        self.correction_config.SITE_ID = "site4"
        mask = pl.col("SITE_ID").eq(self.correction_config.SITE_ID)
        result = add(self.df, self.correction_config, "value_PRFLAG", mask)
        assert_frame_equal(result, self.df)


class TestMultiply(unittest.TestCase):
    def setUp(self):
        self.df = create_test_data()
        self.correction_config = Mock(
            VARIABLE="value",
            CORRECTION_FACTOR=2.0,
            METHOD_ID="MULTIPLY",
        )

    def test_multiply_simple(self):
        """ Test that the multiply function works across the full DataFrame
        """
        result = multiply(self.df, self.correction_config, "value_PRFLAG")
        expected = pl.DataFrame({
            "SITE_ID": ["site1", "site2", "site3"],
            "value": [20., 40., 60.],
            "value_PRFLAG": ["MULTIPLY", "MULTIPLY", "MULTIPLY"],
        })

        assert_frame_equal(result, expected)

    def test_multiply_mask(self):
        """ Test that the multiply function works with a mask clause
        """
        mask = pl.col("SITE_ID").eq("site2")
        result = multiply(self.df, self.correction_config, "value_PRFLAG", mask)
        expected = pl.DataFrame({
            "SITE_ID": ["site1", "site2", "site3"],
            "value": [10., 40., 30.],
            "value_PRFLAG": [None, "MULTIPLY", None],
        })

        assert_frame_equal(result, expected)

    def test_no_matching_rows(self):
        """ Test when no rows match the condition
        """
        self.correction_config.SITE_ID = "site4"
        mask = pl.col("SITE_ID").eq(self.correction_config.SITE_ID)
        result = multiply(self.df, self.correction_config, "value_PRFLAG", mask)
        assert_frame_equal(result, self.df)

class TestPower(unittest.TestCase):
    def setUp(self):
        self.df = create_test_data()
        self.correction_config = Mock(
            VARIABLE="value",
            CORRECTION_FACTOR=2.0,
            METHOD_ID="POWER",
        )

    def test_power_simple(self):
        """ Test that the power function works across the full DataFrame
        """
        result = power(self.df, self.correction_config, "value_PRFLAG")
        expected = pl.DataFrame({
            "SITE_ID": ["site1", "site2", "site3"],
            "value": [100., 400., 900.],
            "value_PRFLAG": ["POWER", "POWER", "POWER"],
        })

        assert_frame_equal(result, expected)

    def test_power_mask(self):
        """ Test that the power function works with a mask clause
        """
        mask = pl.col("SITE_ID").eq("site2")
        result = power(self.df, self.correction_config, "value_PRFLAG", mask)
        expected = pl.DataFrame({
            "SITE_ID": ["site1", "site2", "site3"],
            "value": [10., 400., 30.],
            "value_PRFLAG": [None, "POWER", None],
        })

        assert_frame_equal(result, expected)

    def test_no_matching_rows(self):
        """ Test when no rows match the condition
        """
        self.correction_config.SITE_ID = "site4"
        mask = pl.col("SITE_ID").eq(self.correction_config.SITE_ID)
        result = power(self.df, self.correction_config, "value_PRFLAG", mask)
        assert_frame_equal(result, self.df)
