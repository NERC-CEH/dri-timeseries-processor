import unittest
from unittest.mock import Mock

import polars as pl
from polars.testing import assert_frame_equal

from dritimeseriesprocessor.preprocessing.operations import _when_then_wrapper, add, multiply


def create_test_data():
    return pl.DataFrame({
        "SITE_ID": ["site1", "site2", "site3"],
        "value": [10., 20., 30.]
    })


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
        result = add(self.df, self.correction_config)
        expected = pl.DataFrame({
            "SITE_ID": ["site1", "site2", "site3"],
            "value": [110., 120., 130.]
        })

        assert_frame_equal(result, expected)

    def test_add_mask(self):
        """ Test that the add function works with a mask clause
        """
        mask = pl.col("SITE_ID").eq("site1")
        result = add(self.df, self.correction_config, mask)
        expected = pl.DataFrame({
            "SITE_ID": ["site1", "site2", "site3"],
            "value": [110., 20., 30.]
        })

        assert_frame_equal(result, expected)

    def test_no_matching_rows(self):
        """ Test when no rows match the condition
        """
        self.correction_config.SITE_ID = "site4"
        mask = pl.col("SITE_ID").eq(self.correction_config.SITE_ID)
        result = add(self.df, self.correction_config, mask)
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
        result = multiply(self.df, self.correction_config)
        expected = pl.DataFrame({
            "SITE_ID": ["site1", "site2", "site3"],
            "value": [20., 40., 60.]
        })

        assert_frame_equal(result, expected)

    def test_multiply_mask(self):
        """ Test that the multiply function works with a mask clause
        """
        mask = pl.col("SITE_ID").eq("site2")
        result = multiply(self.df, self.correction_config, mask)
        expected = pl.DataFrame({
            "SITE_ID": ["site1", "site2", "site3"],
            "value": [10., 40., 30.]
        })

        assert_frame_equal(result, expected)

    def test_no_matching_rows(self):
        """ Test when no rows match the condition
        """
        self.correction_config.SITE_ID = "site4"
        mask = pl.col("SITE_ID").eq(self.correction_config.SITE_ID)
        result = multiply(self.df, self.correction_config, mask)
        assert_frame_equal(result, self.df)


class TestWhenThenWrapper(unittest.TestCase):
    def setUp(self):
        self.df = pl.DataFrame({
            "SITE_ID": ["site1", "site1", "site2", "site3"],
            "value": [10, 20, 30, 40]
        })

    def test_basic_when_then(self):
        """ Test basic when-then-otherwise logic returns expected correction to column.
        """
        when = pl.col("SITE_ID").eq("site1")
        then = pl.col("value").mul(2)
        otherwise = pl.col("value")

        result = _when_then_wrapper(self.df, when, then, otherwise)
        expected = pl.DataFrame({
            "SITE_ID": ["site1", "site1", "site2", "site3"],
            "value": [20, 40, 30, 40]
        })

        assert_frame_equal(result, expected)

    def test_alternative_otherwise(self):
        """ Test basic when-then-otherwise logic, but with an expression in the otherwise.
        """
        when = pl.col("SITE_ID").eq("site1")
        then = pl.col("value").mul(2)
        otherwise = pl.col("value").mul(10)

        result = _when_then_wrapper(self.df, when, then, otherwise)
        expected = pl.DataFrame({
            "SITE_ID": ["site1", "site1", "site2", "site3"],
            "value": [20, 40, 300, 400]
        })

        assert_frame_equal(result, expected)

    def test_no_condition_met(self):
        """ Test that the dataframe is not altered when no condition is met.
        """
        when = pl.col("SITE_ID").eq("site4")
        then = pl.col("value").mul(2)
        otherwise = pl.col("value")

        result = _when_then_wrapper(self.df, when, then, otherwise)
        expected = self.df

        assert_frame_equal(result, expected)

    def test_all_rows_meet_condition(self):
        """ Test when condition that applies to all rows.
        """
        when = pl.col("SITE_ID").is_in(["site1", "site2", "site3"])
        then = pl.col("value").mul(2)
        otherwise = pl.col("value")

        result = _when_then_wrapper(self.df, when, then, otherwise)
        expected = pl.DataFrame({
            "SITE_ID": ["site1", "site1", "site2", "site3"],
            "value": [20, 40, 60, 80]
        })

        assert_frame_equal(result, expected)

    def test_function_for_then(self):
        """ Test that sending a more complication function for the then expression works as expected.
        """

        def _dummy():
            # Multiply value by 10, cast to string and append to the site ID
            return (pl.col("value").mul(10)).cast(str) + pl.col("SITE_ID")

        when = pl.col("SITE_ID").is_in(["site1", "site2", "site3"])
        then = _dummy()
        otherwise = pl.col("value")

        result = _when_then_wrapper(self.df, when, then, otherwise)
        expected = pl.DataFrame({
            "SITE_ID": ["site1", "site1", "site2", "site3"],
            "value": ["100site1", "200site1", "300site2", "400site3"]
        })

        assert_frame_equal(result, expected)
