import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch

import pandas as pd
import polars as pl

from dritimeseriesprocessor.flagging.flagger import add_initial_core_flags
from dritimeseriesprocessor.infilling.infiller import run_infilling
from time_stream import Period, TimeSeries


def mock_infill_method1(ts, _, flag_column, *args, **kwargs):
    ts.add_flag(flag_column, "method1")
    return ts


def mock_infill_method2(ts, _, flag_column, *args, **kwargs):
    ts.add_flag(flag_column, "method2")
    return ts


class TestRunInfilling(unittest.TestCase):
    def setUp(self):
        """
        Set up common test data and mocks.
        """
        ta_data = pl.DataFrame({
            "time": pd.date_range(start="2023-01-01", periods=10, freq="H"),
            "temperature": [20.0, 21.0, None, None, 22.0, 23.0, None, 24.0, 25.0, 26.0],
        })
        pa_data = pl.DataFrame({
            "time": pd.date_range(start="2023-01-01", periods=10, freq="H"),
            "pressure": [1010.0, 1011.0, 1012.0, None, 1013.0, None, 1014.0, 1015.0, None, 1016.0],
        })
        resolution = Period.of_hours(1)
        periodicity = Period.of_hours(1)
        ta_ts = TimeSeries(ta_data, "time", resolution, periodicity)
        ta_ts = add_initial_core_flags(ta_ts)

        pa_ts = TimeSeries(pa_data, "time", resolution, periodicity)
        pa_ts = add_initial_core_flags(pa_ts)

        site_id = "SITE1"
        self.ta_ts_id = f"{site_id}_ta_30min_raw"
        self.pa_ts_id = f"{site_id}_pa_30min_raw"

        self.ts_ids = {
            self.ta_ts_id: {
                "data": ta_ts,
            },
            self.pa_ts_id: {
                "data": pa_ts,
            }
        }

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
            "site_id": site_id,
            "ts_id": self.ta_ts_id,
            "configs": [type("DummyMethodConfig", (), {
                "name": "method1",
                "interval": (datetime(2000, 1, 1), None),
                "observation_interval": (datetime(2023, 1, 1), None),
                "parameters": {
                    "max_gap_size": 3
                },
            })],
            "annotations": {"data-processing-configuration-priority": 1}
        })()

        self.infill_config2 = type("DummyInfillConfig", (), {
            "site_id": site_id,
            "ts_id": self.ta_ts_id,
            "configs": [type("DummyMethodConfig", (), {
                "name": "method2",
                "interval": (datetime(2000, 1, 1), None),
                "observation_interval": (datetime(2023, 1, 1), None),
                "parameters": {
                    "max_gap_size": 6
                },
            })],
            "annotations": {"data-processing-configuration-priority": 2}
        })()

    @patch('dritimeseriesprocessor.infilling.infiller.load_config')
    @patch('dritimeseriesprocessor.infilling.infiller.get_infill_methods')
    def test_run_infilling_no_methods(self, mock_get_methods, mock_get_configs):
        """Test run_infilling when no infill methods are defined."""
        mock_get_configs.return_value = [MagicMock()]
        mock_get_methods.return_value = {}
        result = run_infilling(self.ts_ids)

        self.assertEqual(result, self.ts_ids)

    @patch('dritimeseriesprocessor.infilling.infiller.load_config')
    @patch('dritimeseriesprocessor.infilling.infiller.get_infill_methods')
    def test_run_infilling_success(self, mock_get_methods, mock_get_configs):
        """Test basic results of run_infilling.
        """
        mock_get_configs.return_value = [self.infill_config1]
        mock_get_methods.return_value = self.mock_methods_dict

        # Call function
        result = run_infilling(self.ts_ids)

        # Check flag system added
        self.assertIn('infill_flags', result[self.ta_ts_id]["data"].flag_systems)
        # Check columns added
        self.assertIn('temperature_INFILL_FLAG', result[self.ta_ts_id]["data"].columns)
        # Check flag values (from mock functions) have been added
        self.assertEqual(result[self.ta_ts_id]["data"].df['temperature_INFILL_FLAG'].to_list(), [1, 1, 1, 1, 1, 1, 1, 1, 1, 1])

    @patch('dritimeseriesprocessor.infilling.infiller.load_config')
    @patch('dritimeseriesprocessor.infilling.infiller.get_infill_methods')
    def test_run_infilling_multiple_methods(self, mock_get_methods, mock_get_configs):
        """ Test run_infilling with multiple infill methods for a single column.
        Checks if the methods are applied in the correct order (by priority).
        """
        mock_get_configs.return_value = [self.infill_config1, self.infill_config2]
        mock_get_methods.return_value = self.mock_methods_dict

        # Call function
        result = run_infilling(self.ts_ids)

        # Check flag system added
        self.assertIn('infill_flags', result[self.ta_ts_id]["data"].flag_systems)
        # Check columns added
        self.assertIn('temperature_INFILL_FLAG', result[self.ta_ts_id]["data"].columns)
        # Check flag values (from mock functions) have been added
        self.assertEqual(result[self.ta_ts_id]["data"].df['temperature_INFILL_FLAG'].to_list(), [3, 3, 3, 3, 3, 3, 3, 3, 3, 3])
