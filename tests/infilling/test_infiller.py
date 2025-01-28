import unittest
from unittest.mock import patch, MagicMock
import numpy as np
import polars as pl
from polars.testing import assert_frame_equal
from datetime import datetime
from dritimeseriesprocessor.infilling.infiller import (
    infill_flag_column_name,
    run_infilling
)
from time_series import TimeSeries, Period


def mock_linear_interpolation(ts, column, flag_column, max_gap_size=None):
    ts.add_flag(flag_column, "INTERP_LINEAR")
    return ts


def mock_forward_fill(ts, column, flag_column, max_gap_size=None):
    ts.add_flag(flag_column, "FORWARD_FILL")
    return ts


class TestInfillFlagColumnName(unittest.TestCase):
    """Unit tests for the infill_flag_column_name function.
    """
    def test_standard_column_name(self):
        """
        Test that the function correctly appends '_INFILL_FLAG' to a standard column name.
        """
        self.assertEqual(infill_flag_column_name('data'), 'data_INFILL_FLAG')


test_INFILL_METHODS = {
    "INTERP_LINEAR": mock_linear_interpolation,
    "FORWARD_FILL": mock_forward_fill
}

class TestRunInfilling(unittest.TestCase):
    """
    Test suite for the run_infilling function.
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
            'humidity': [50, 55, None, None, 60, None, 70]
        })

        resolution = Period.of_days(1)
        periodicity = Period.of_days(1)
        self.ts = TimeSeries(
            data,
            "time",
            resolution,
            periodicity
        )

        self.mock_infill_methods = {
            'INTERP_LINEAR': MagicMock(
                name="Linear interpolation",
                description="straight line interpolation",
                requirements={'window': 1},
                id=1
            ),
            'FORWARD_FILL': MagicMock(
                name="Forward fill",
                description="filling with the last known value",
                requirements={'window': 1},
                id=2
            ),
        }

        self.mock_var_config = {
            'temperature': {
                'P1D': MagicMock(methods=[
                    MagicMock(method='INTERP_LINEAR', priority=1, constraints={'max_gap_size': 2})
                ])
            },
            'humidity': {
                'P1D': MagicMock(methods=[
                    MagicMock(method='FORWARD_FILL', priority=1, constraints={'max_gap_size': 1})
                ])
            }
        }

        self.mock_INFILL_METHODS = {
            "INTERP_LINEAR": mock_linear_interpolation,
            "FORWARD_FILL": mock_forward_fill
        }

    @patch('dritimeseriesprocessor.infilling.infiller.get_infill_config')
    @patch('dritimeseriesprocessor.infilling.infiller.INFILL_METHODS', new=test_INFILL_METHODS)
    def test_run_infilling_basic(self, mock_get_infill_config):
        """
        Test basic functionality of run_infilling.
        Checks if the function add the flag system, add the flag columns, and runs the infill methods.
        """
        mock_get_infill_config.side_effect = lambda key: self.mock_var_config if key == 'variables' else self.mock_infill_methods

        result = run_infilling(self.ts)

        # Check flag system added
        self.assertIn('infill_flags', result.flag_systems)
        # Check columns added
        self.assertIn('temperature_INFILL_FLAG', result.columns)
        self.assertIn('humidity_INFILL_FLAG', result.columns)
        # Check flag values (from mock functions) have been added
        self.assertEqual(result.df['temperature_INFILL_FLAG'].to_list(), [1, 1, 1, 1, 1, 1, 1])
        self.assertEqual(result.df['humidity_INFILL_FLAG'].to_list(), [2, 2, 2, 2, 2, 2, 2])

    @patch('dritimeseriesprocessor.infilling.infiller.get_infill_config')
    def test_run_infilling_no_config(self, mock_get_infill_config):
        """
        Test run_infilling when no infill config is available for any column.
        Checks if the function returns the original DataFrame unchanged.
        """
        mock_get_infill_config.side_effect = lambda key: self.mock_var_config if key == 'variables' else {}

        result = run_infilling(self.ts)

        assert_frame_equal(result.df, self.ts.df)

    @patch('dritimeseriesprocessor.infilling.infiller.get_infill_config')
    def test_run_infilling_no_methods(self, mock_get_infill_config):
        """
        Test run_infilling when infill config exists but no methods are specified.
        Checks if the function returns the original DataFrame unchanged.
        """
        mock_config = {'temperature': {'PT1M': MagicMock(methods=[])}}
        mock_get_infill_config.side_effect = lambda key: mock_config if key == 'variables' else self.mock_infill_methods

        result = run_infilling(self.ts)

        assert_frame_equal(result.df, self.ts.df)

    @patch('dritimeseriesprocessor.infilling.infiller.get_infill_config')
    @patch('dritimeseriesprocessor.infilling.infiller.INFILL_METHODS', new=test_INFILL_METHODS)
    def test_run_infilling_multiple_methods(self, mock_get_infill_config):
        """
        Test run_infilling with multiple infill methods for a single column.
        Checks if the methods are applied in the correct order (by priority).
        """
        mock_config = {
            'temperature': {
                'P1D': MagicMock(methods=[
                    MagicMock(method='INTERP_LINEAR', priority=2, constraints={'max_gap_size': 2}, id=1),
                    MagicMock(method='FORWARD_FILL', priority=1, constraints={'max_gap_size': 1}, id=2)
                ])
            }
        }
        mock_get_infill_config.side_effect = lambda key: mock_config if key == 'variables' else self.mock_infill_methods

        result = run_infilling(self.ts)

        # Check flag values (from both mock functions) have been added
        self.assertEqual(result.df['temperature_INFILL_FLAG'].to_list(), [3, 3, 3, 3, 3, 3, 3])


    @patch('dritimeseriesprocessor.infilling.infiller.get_infill_config')
    @patch('dritimeseriesprocessor.infilling.infiller.INFILL_METHODS', new=test_INFILL_METHODS)
    def test_run_infilling_default_resolution(self, mock_get_infill_config):
        """
        Test run_infilling using default resolution when PT1M is not available.
        Checks if the function correctly falls back to the default resolution.
        """
        mock_config = {
            'temperature': {
                'default': MagicMock(methods=[
                    MagicMock(method='INTERP_LINEAR', priority=1, constraints={'max_gap_size': 2}, id=1)
                ])
            }
        }
        mock_get_infill_config.side_effect = lambda key: mock_config if key == 'variables' else self.mock_infill_methods

        result = run_infilling(self.ts)

        self.assertEqual(result.df['temperature_INFILL_FLAG'].to_list(), [1, 1, 1, 1, 1, 1, 1])
