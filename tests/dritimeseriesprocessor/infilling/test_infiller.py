import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch

import pandas as pd
import polars as pl

from dritimeseriesprocessor.infilling.infiller import infill_flag_column_name, run_infilling
from time_series import Period, TimeSeries


def mock_infill_method1(ts, _, flag_column, *args, **kwargs):
    ts.add_flag(flag_column, "method1")
    return ts


def mock_infill_method2(ts, _, flag_column, *args, **kwargs):
    ts.add_flag(flag_column, "method2")
    return ts


class TestInfillFlagColumnName(unittest.TestCase):
    """Unit tests for the infill_flag_column_name function.
    """
    def test_standard_column_name(self):
        """
        Test that the function correctly appends '_INFILL_FLAG' to a standard column name.
        """
        self.assertEqual(infill_flag_column_name('data'), 'data_INFILL_FLAG')


class TestRunInfilling(unittest.TestCase):
    def setUp(self):
        """
        Set up common test data and mocks.
        """
        data = pl.DataFrame({
            "time": pd.date_range(start="2023-01-01", periods=10, freq="H"),
            "temperature": [20.0, 21.0, None, None, 22.0, 23.0, None, 24.0, 25.0, 26.0],
            "pressure": [1010, 1012, 1013, None, None, 1015, 1016, 1017, 1018, 1019],
        })
        resolution = Period.of_hours(1)
        periodicity = Period.of_hours(1)
        self.ts = TimeSeries(data, "time", resolution, periodicity)
        self.site_id = "SITE1"

        # Set up dummy infilling methods
        infill_method1 = type("DummyInfillMethod", (), {
            "method_id": 1,
            "name": "method1",
            "description": "description of method1",
            "function_name": "run_method1",
            "__call__": lambda self, *args, **kwargs: mock_infill_method1(*args, **kwargs),
        })()

        infill_method2 = type("DummyInfillMethod", (), {
            "method_id": 2,
            "name": "method2",
            "description": "description of method2",
            "function_name": "run_method2",
            "__call__": lambda self, *args, **kwargs: mock_infill_method2(*args, **kwargs),
        })()

        self.mock_methods_dict = {
            "method1": infill_method1,
            "method2": infill_method2,
        }

        # Set up infilling configs
        self.infill_config1 = type("DummyInfillConfig", (), {
            "site_id": self.site_id,
            "time_series_name": "temperature",
            "priority": 1,
            "method": type("DummyMethodConfig", (), {
                "name": "method1",
                "start_date": datetime(2023, 1, 1),
                "parameters": {
                    "max_gap_size": 3
                },
            })
        })()

        self.infill_config2 = type("DummyInfillConfig", (), {
            "site_id": self.site_id,
            "time_series_name": "temperature",
            "priority": 2,
            "method": type("DummyMethodConfig", (), {
                "name": "method2",
                "start_date": datetime(2023, 1, 1),
                "parameters": {
                    "max_gap_size": 6
                },
            })
        })()

    @patch('dritimeseriesprocessor.infilling.infiller.get_infill_configs')
    def test_run_infilling_no_configs(self, mock_get_configs):
        """Test run_infilling when no configs are found for the site."""
        site_id = "NONEXISTENT"

        mock_get_configs.return_value = {}
        result = run_infilling(self.ts, site_id)

        self.assertEqual(result, self.ts)

    @patch('dritimeseriesprocessor.infilling.infiller.get_infill_configs')
    @patch('dritimeseriesprocessor.infilling.infiller.get_infill_methods')
    def test_run_infilling_no_methods(self, mock_get_methods, mock_get_configs):
        """Test run_infilling when no infill methods are defined."""
        mock_get_configs.return_value = {
            self.site_id: {
                "PT1H": {
                    "temperature":  [MagicMock()]
                }
            }
        }
        mock_get_methods.return_value = {}
        result = run_infilling(self.ts, self.site_id)

        self.assertEqual(result, self.ts)

    @patch('dritimeseriesprocessor.infilling.infiller.get_infill_configs')
    @patch('dritimeseriesprocessor.infilling.infiller.get_infill_methods')
    def test_run_infilling_success(self, mock_get_methods, mock_get_configs):
        """Test basic results of run_infilling.
        """
        mock_get_configs.return_value = {
            self.site_id: {
                "PT1H": {
                    "temperature": [self.infill_config1],
                    # pressure has no methods
                }
            }
        }
        mock_get_methods.return_value = self.mock_methods_dict

        # Call function
        result = run_infilling(self.ts, self.site_id)

        # Check flag system added
        self.assertIn('infill_flags', result.flag_systems)
        # Check columns added
        self.assertIn('temperature_INFILL_FLAG', result.columns)
        self.assertNotIn('pressure_INFILL_FLAG', result.columns)  # pressure has no methods so shouldn't have flag col
        # Check flag values (from mock functions) have been added
        self.assertEqual(result.df['temperature_INFILL_FLAG'].to_list(), [1, 1, 1, 1, 1, 1, 1, 1, 1, 1])

    @patch('dritimeseriesprocessor.infilling.infiller.get_infill_configs')
    @patch('dritimeseriesprocessor.infilling.infiller.get_infill_methods')
    def test_run_infilling_multiple_methods(self, mock_get_methods, mock_get_configs):
        """ Test run_infilling with multiple infill methods for a single column.
        Checks if the methods are applied in the correct order (by priority).
        """
        mock_get_configs.return_value = {
            self.site_id: {
                "PT1H": {
                    "temperature": [self.infill_config1, self.infill_config2],
                    # pressure has no methods
                }
            }
        }
        mock_get_methods.return_value = self.mock_methods_dict

        # Call function
        result = run_infilling(self.ts, self.site_id)

        # Check flag system added
        self.assertIn('infill_flags', result.flag_systems)
        # Check columns added
        self.assertIn('temperature_INFILL_FLAG', result.columns)
        # Check flag values (from both mock functions) have been added
        self.assertEqual(result.df['temperature_INFILL_FLAG'].to_list(), [3, 3, 3, 3, 3, 3, 3, 3, 3, 3])
