import unittest

import polars as pl
from datetime import datetime

from time_stream import TimeSeries, Period
from dritimeseriesprocessor.quality_control.utils import column_threshold_check


class TestColumnThresholdCheck(unittest.TestCase):
    def setUp(self):
        a_data = pl.DataFrame({
            'time': [
                datetime(2023, 8, 10),
                datetime(2023, 8, 11),
                datetime(2023, 8, 12),
                datetime(2023, 8, 13),
            ],
            "value_a": [5., 10., 20., 30.],
        })

        b_data = pl.DataFrame({
            'time': [
                datetime(2023, 8, 10),
                datetime(2023, 8, 11),
                datetime(2023, 8, 12),
                datetime(2023, 8, 13),
            ],
            "value_b": [1.0, 1.1, 1.2, 1.3],
        })

        c_data = pl.DataFrame({
            'time': [
                datetime(2023, 8, 10),
                datetime(2023, 8, 11),
                datetime(2023, 8, 12),
                datetime(2023, 8, 13),
            ],
            "value_c": [None, 50., 100., None],
        })

        resolution = Period.of_days(1)
        periodicity = Period.of_days(1)

        self.ts_a = TimeSeries(a_data, "time", resolution, periodicity, metadata={"column_name": "value_a"})
        self.ts_b = TimeSeries(b_data, "time", resolution, periodicity, metadata={"column_name": "value_b"})
        self.ts_c = TimeSeries(c_data, "time", resolution, periodicity, metadata={"column_name": "value_c"})

        self.ts_a.add_flag_system("qc_flags", {"TEST": 1})
        self.ts_b.add_flag_system("qc_flags", {"TEST": 1})
        self.ts_c.add_flag_system("qc_flags", {"TEST": 1})

        self.ts_b.init_flag_column("qc_flags", "value_b_QC_FLAG")
        self.ts_c.init_flag_column("qc_flags", "value_c_QC_FLAG")


    def test_greater_than(self):
        """ Test the column threshold check function with '>' operator.
        """
        result = column_threshold_check(self.ts_b, self.ts_a, "value_b_QC_FLAG", 10, ">", 1)
        self.assertEqual(result.df['value_b_QC_FLAG'].to_list(), [0, 0, 1, 1])

    def test_greater_than_or_equal(self):
        """ Test the column threshold check function with '>=' operator.
        """
        result = column_threshold_check(self.ts_b, self.ts_a, "value_b_QC_FLAG", 10, ">=", 1)
        self.assertEqual(result.df['value_b_QC_FLAG'].to_list(), [0, 1, 1, 1])

    def test_less_than(self):
        """ Test the column threshold check function with '<' operator.
        """
        result = column_threshold_check(self.ts_b, self.ts_a, "value_b_QC_FLAG", 10, "<", 1)
        self.assertEqual(result.df['value_b_QC_FLAG'].to_list(), [1, 0, 0, 0])

    def test_less_than_or_equal(self):
        """ Test the column threshold check function with '<=' operator.
        """
        result = column_threshold_check(self.ts_b, self.ts_a, "value_b_QC_FLAG", 10, "<=", 1)
        self.assertEqual(result.df['value_b_QC_FLAG'].to_list(), [1, 1, 0, 0])
        
    def test_equal(self):
        """ Test the column threshold check function with '==' operator.
        """
        result = column_threshold_check(self.ts_b, self.ts_a, "value_b_QC_FLAG", 10, "==", 1)
        self.assertEqual(result.df['value_b_QC_FLAG'].to_list(), [0, 1, 0, 0])
        
    def test_not_equal(self):
        """ Test the column threshold check function with '!=' operator.
        """
        result = column_threshold_check(self.ts_b, self.ts_a, "value_b_QC_FLAG", 10, "!=", 1)
        self.assertEqual(result.df['value_b_QC_FLAG'].to_list(), [1, 0, 1, 1])

    def test_flag_na_when_true(self):
        """ Test that setting flag_na to True means that any NULL values in the check column are treated as failing
        the QC check (so qc flag set in result)
        """
        result = column_threshold_check(self.ts_b, self.ts_c, "value_b_QC_FLAG", 10, ">", 1, flag_na=True)
        self.assertEqual(result.df['value_b_QC_FLAG'].to_list(), [1, 1, 1, 1])

    def test_flag_na_when_false(self):
        """ Test that setting flag_na to False means that any NULL values in the check column are ignored in
        the QC check (so qc flag not set in result)
        """
        result = column_threshold_check(self.ts_b, self.ts_c, "value_b_QC_FLAG", 10, ">", 1, flag_na=False)
        self.assertEqual(result.df['value_b_QC_FLAG'].to_list(), [0, 1, 1, 0])

    def test_missing_flag_column(self):
        """ Test that a missing qc column raises error
        """
        with self.assertRaises(UserWarning):
            column_threshold_check(self.ts_b, self.ts_a, "missing_QC_FLAG", 10, ">", 1)

    def test_invalid_operator(self):
        """ Test that invalid operator raises error
        """
        with self.assertRaises(ValueError):
            column_threshold_check(self.ts_b, self.ts_a, "value_b_QC_FLAG", 10, ">>", 1)
