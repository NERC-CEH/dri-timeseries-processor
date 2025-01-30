import pytest
import unittest
import polars as pl
from time_series import TimeSeries
from datetime import datetime

from dritimeseriesprocessor.flagging.flagger import (
    initialise_core_flag_system,
    add_initial_core_flags,
    update_preprocess_core_flags,
    update_quality_control_core_flags,
    update_infill_core_flags,
    core_flag_column_name,
    missing_expr,
)


class TestMissingExpr(unittest.TestCase):
    def test_missing_expr(self):
        """Test the expression for detecting missing values."""
        expr = missing_expr("value")
        df = pl.DataFrame({"value": [10, None, 30, float('nan'), 50]}, strict=False)
        result = df.with_columns(expr.alias("is_missing"))
        self.assertEqual(result["is_missing"].to_list(), [False, True, False, True, False])


class TestCoreFlagColumnName(unittest.TestCase):
    def test_core_flag_column_name(self):
        """Test the generation of core flag column names."""
        self.assertEqual(core_flag_column_name("value"), "value_CORE_FLAG")
        self.assertEqual(core_flag_column_name("temperature"), "temperature_CORE_FLAG")


class TestFlagger(unittest.TestCase):
    def setUp(self):
        data = {
            "timestamp": [
                datetime(2023, 1, 1, 0, 0),
                datetime(2023, 1, 1, 1, 0),
                datetime(2023, 1, 1, 2, 0),
                datetime(2023, 1, 1, 3, 0),
                datetime(2023, 1, 1, 4, 0),
            ],
            "value": [10, None, 30, None, 50],
        }
        self.sample_timeseries = TimeSeries(
            pl.DataFrame(data),
            time_name="timestamp",
        )
        self.sample_timeseries.add_flag_system("pr_flags", {"ADD": 1})
        self.sample_timeseries.init_flag_column("pr_flags", "value_PR_FLAG", [1, 0, 0, 0, 1])
        self.sample_timeseries.add_flag_system("qc_flags", {"RANGE": 1})
        self.sample_timeseries.init_flag_column("qc_flags", "value_QC_FLAG", [0, 1, 0, 1, 0])
        self.sample_timeseries.add_flag_system("infill_flags", {"INTERP": 1})
        self.sample_timeseries.init_flag_column("infill_flags", "value_INFILL_FLAG", [0, 0, 1, 0, 0])


class TestInitialiseCoreFlagSystem(TestFlagger):
    def test_initialise_core_flag_system(self):
        """Test the initialisation of the core flag system."""
        ts = initialise_core_flag_system(self.sample_timeseries)
        self.assertIn("core_flags", ts.flag_systems)


class TestAddInitialCoreFlags(TestFlagger):
    def test_add_initial_core_flags(self):
        """Test the initial core flags of 'unchecked' (32) and 'missing' (4) are added correctly."""
        ts = add_initial_core_flags(self.sample_timeseries)
        flag_col = core_flag_column_name("value")
        self.assertIn(flag_col, ts.flag_columns)
        self.assertEqual(list(ts.df[flag_col]), [32, 36, 32, 36, 32])


class TestUpdatePreprocessCoreFlags(TestFlagger):
    def test_update_preprocess_core_flags(self):
        """Test the the core flag column is updated with 'corrected' core flag (1)."""
        ts = add_initial_core_flags(self.sample_timeseries)
        ts = update_preprocess_core_flags(self.sample_timeseries)
        flag_col = core_flag_column_name("value")
        self.assertEqual(list(ts.df[flag_col]), [33, 36, 32, 36, 33])
    
    def test_no_core_flag_column(self):
        """Test that an error is raised if the core flag column is not found."""
        with self.assertRaises(ValueError):
            update_preprocess_core_flags(self.sample_timeseries)


class TestUpdateQualityControlCoreFlags(TestFlagger):
    def test_update_quality_control_core_flags(self):
        """Test the the core flag column is updated with the 'removed' core flag (8),
        and the 'unchecked' core flag (32) is removed."""
        # Init core flags so the uncheked flag is present.
        ts = add_initial_core_flags(self.sample_timeseries)
        ts = update_quality_control_core_flags(ts)
        flag_col = core_flag_column_name("value")
        # Should be left with missing (4) plus removed (8) flags.
        self.assertEqual(list(ts.df[flag_col]), [0, 12, 0, 12, 0])

    def test_unchecked_not_removed(self):
        """Test that the 'unchecked' flag is not removed when the QC flag is missing."""
        # Init core flags so the uncheked flag is present.
        ts = add_initial_core_flags(self.sample_timeseries)
        ts.df = ts.df.with_columns(pl.Series("value_QC_FLAG", [0, None, 0, None, 0]))
        ts = update_quality_control_core_flags(ts)
        flag_col = core_flag_column_name("value")
        # Should be left with missing (4) plus unchecked (32) flags.
        self.assertEqual(list(ts.df[flag_col]), [0, 36, 0, 36, 0])

    def test_no_core_flag_column(self):
        """Test that an error is raised if the core flag column is not found."""
        with self.assertRaises(ValueError):
            update_quality_control_core_flags(self.sample_timeseries)


class TestUpdateInfillCoreFlags(TestFlagger):
    def test_update_infill_core_flags(self):
        """Test the the core flag column is updated with the 'interpolated' core flag (2)."""
        ts = add_initial_core_flags(self.sample_timeseries)
        ts = update_infill_core_flags(self.sample_timeseries)
        flag_col = core_flag_column_name("value")
        self.assertEqual(list(ts.df[flag_col]), [32, 36, 34, 36, 32])

    def test_no_core_flag_column(self):
        """Test that an error is raised if the core flag column is not found."""
        with self.assertRaises(ValueError):
            update_infill_core_flags(self.sample_timeseries)