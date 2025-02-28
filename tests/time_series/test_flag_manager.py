from datetime import datetime
import unittest

from parameterized import parameterized
import polars as pl
from polars.testing import assert_series_equal

from time_series import TimeSeries
from time_series.bitwise import BitwiseFlag
from time_series.columns import FlagColumn
from time_series.flag_manager import TimeSeriesFlagManager


class BaseFlagManagerTest(unittest.TestCase):
    """Base class for setting up test fixtures for TimeSeriesFlagManager tests."""

    @classmethod
    def setUpClass(cls):
        """Set up a mock TimeSeries and FlagManager for testing."""
        cls.df = pl.DataFrame({
            "time": [datetime(2024, 1, 1), datetime(2024, 1, 2), datetime(2024, 1, 3)],
            "data_col": [10, 20, 30],
            "existing_flags": [0, 1, 2],
            "more_flags": [0, 1, 2],
            "more_flags2": [0, 1, 2]
        })
        cls.flag_system = {
            "OUT_OF_RANGE": 1,
            "SPIKE": 2,
            "LOW_BATTERY": 4
        }
        cls.flag_systems = {"quality_control": BitwiseFlag("quality_control", cls.flag_system)}
        cls.ts = TimeSeries(df=cls.df, time_name="time", flag_systems=cls.flag_systems)


class TestAddFlagSystem(BaseFlagManagerTest):
    def test_add_valid_dict_flag_system(self):
        """Test adding a new valid dict based flag system."""
        flag_manager = TimeSeriesFlagManager(self.ts, self.flag_systems)
        new_flag_system = {"FLAG_A": 1, "FLAG_B": 2, "FLAG_C": 4}
        flag_manager.add_flag_system("new_flags", new_flag_system)
        self.assertIn("new_flags", flag_manager.flag_systems)

    def test_add_valid_class_flag_system(self):
        """Test adding a new valid bitwise class based flag system."""
        flag_manager = TimeSeriesFlagManager(self.ts, self.flag_systems)
        new_flag_system = BitwiseFlag("new_flags", {"FLAG_A": 1, "FLAG_B": 2, "FLAG_C": 4})
        flag_manager.add_flag_system("new_flags", new_flag_system)
        self.assertIn("new_flags", flag_manager.flag_systems)

    def test_add_duplicate_flag_system_raises_error(self):
        """Test adding a duplicate flag system raises error."""
        flag_manager = TimeSeriesFlagManager(self.ts, self.flag_systems)
        new_flag_system = {"FLAG_A": 1, "FLAG_B": 2, "FLAG_C": 4}
        with self.assertRaises(KeyError):
            flag_manager.add_flag_system("quality_control", new_flag_system)


class TestInitFlagColumn(BaseFlagManagerTest):
    def setUp(self):
        super().setUpClass()

    def test_init_flag_column_success(self):
        """Test initializing a flag column with a valid flag system."""
        flag_manager = TimeSeriesFlagManager(self.ts, self.flag_systems)
        flag_manager.init_flag_column("quality_control", "flag_column")

        self.assertIn("flag_column", self.ts.columns)
        self.assertIn("flag_column", self.ts.flag_columns)
        self.assertIsInstance(self.ts.flag_column, FlagColumn)

    def test_init_flag_column_invalid_flag_system_raises_error(self):
        """Test initialising a flag column with a non-existent flag system raises error."""
        flag_manager = TimeSeriesFlagManager(self.ts, self.flag_systems)
        with self.assertRaises(KeyError):
            flag_manager.init_flag_column("bad_system", "flag_column")

    def test_init_flag_column_invalid_column_name_raises_error(self):
        """Test initialising a flag column with a duplicate column name raises error."""
        flag_manager = TimeSeriesFlagManager(self.ts, self.flag_systems)
        with self.assertRaises(KeyError):
            flag_manager.init_flag_column("quality_control", "existing_flags")

    def test_init_flag_column_with_nonzero_default(self):
        """Test initialising a flag column with a default nonzero value."""
        flag_manager = TimeSeriesFlagManager(self.ts, self.flag_systems)
        flag_manager.init_flag_column("quality_control", "flag_column", data=2)

        expected_values = pl.Series("flag_column", [2, 2, 2], dtype=pl.Int64)
        assert_series_equal(self.ts.df["flag_column"], expected_values)

    def test_init_flag_column_with_list_values(self):
        """Test initialising a flag column with a list of values."""
        flag_manager = TimeSeriesFlagManager(self.ts, self.flag_systems)
        flag_manager.init_flag_column("quality_control", "flag_column", data=[1, 2, 4])

        expected_values = pl.Series("flag_column", [1, 2, 4], dtype=pl.Int64)
        pl.testing.assert_series_equal(self.ts.df["flag_column"], expected_values)

    @parameterized.expand([
        ("too_short", [1, 2]),
        ("too_long", [1, 2, 4, 5]),
    ])
    def test_init_flag_column_with_list_wrong_length_raises_error(self, _, new_values):
        """Test that initialising a flag column with a list of incorrect length raises an error."""
        flag_manager = TimeSeriesFlagManager(self.ts, self.flag_systems)
        with self.assertRaises(pl.ShapeError):
            flag_manager.init_flag_column("quality_control", "flag_column", data=new_values)


class TestCheckDataFlagRelationship(BaseFlagManagerTest):
    def setUp(self):
        super().setUpClass()

        new_flag_system = {"FLAG_A": 1, "FLAG_B": 2, "FLAG_C": 4}
        self.ts.add_flag_system("new_flags", new_flag_system)

        self.ts.set_flag_column("quality_control", "existing_flags")
        self.ts.set_flag_column("new_flags", "more_flags")
        self.ts.set_flag_column("quality_control", "more_flags2")

        self.ts.data_col.add_relationship(self.ts.existing_flags)

    def test_check_data_flag_relationship_success(self):
        """ Test that non-related columns with unique flag system passes the check (no errors) """
        TimeSeriesFlagManager.check_data_flag_relationship(self.ts.data_col, self.ts.more_flags)
    
    def test_check_data_flag_relationship_existing_relationship(self):
        """ Test that already related flag column does not error"""
        TimeSeriesFlagManager.check_data_flag_relationship(self.ts.data_col, self.ts.existing_flags)
        
    def test_check_data_flag_relationship_fail(self):
        """ Test that non-related columns with same flag system as a related column fails the check """
        with self.assertRaises(UserWarning):
            TimeSeriesFlagManager.check_data_flag_relationship(self.ts.data_col, self.ts.more_flags2)
