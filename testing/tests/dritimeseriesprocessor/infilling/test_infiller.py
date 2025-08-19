import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch
from typing import Any

import polars as pl

from dritimeseriesprocessor.flagging.flagger import add_initial_core_flags
from dritimeseriesprocessor.infilling.infiller import run_infilling
from time_stream import Period, TimeSeries
from time_stream.infill import InfillMethod


class MockInfillMethod(InfillMethod):
    name = "Mock"
    def __init__(self, **kwargs: Any):
        pass

    def _fill(self, df, infill_column) -> pl.DataFrame:
        return df.with_columns(
            pl.col(infill_column).fill_null(100).alias(f"{infill_column}_{self.name}")
        )


class TestRunInfilling(unittest.TestCase):
    def setUp(self):
        """
        Set up common test data and mocks.
        """
        datetimes = pl.datetime_range(
            start=datetime(2023, 1, 1), end=datetime(2023, 1, 1, 9), interval="1h", eager=True
        )
        ta_data = pl.DataFrame({
            "time": datetimes,
            "temperature": [20.0, 21.0, None, None, 22.0, 23.0, None, 24.0, 25.0, 26.0],
        })
        pa_data = pl.DataFrame({
            "time": datetimes,
            "pressure": [1010.0, 1011.0, 1012.0, None, 1013.0, None, 1014.0, 1015.0, None, 1016.0],
        })
        resolution = Period.of_hours(1)
        periodicity = Period.of_hours(1)
        ta_ts = TimeSeries(ta_data, "time", resolution, periodicity, metadata={"column_name": "temperature"})
        ta_ts = add_initial_core_flags(ta_ts)

        pa_ts = TimeSeries(pa_data, "time", resolution, periodicity, metadata={"column_name": "pressure"})
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
            "function_name": MockInfillMethod
        })()

        infill_method2 = type("DummyInfillMethod", (), {
            "method_id": 2,
            "name": "method2",
            "description": "description of method2",
            "function_name": MockInfillMethod,
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
                    "max_gap_size": 1
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
                    "max_gap_size": 3
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
        self.assertEqual(result[self.ta_ts_id]["data"].df['temperature_INFILL_FLAG'].to_list(), [0, 0, 0, 0, 0, 0, 1, 0, 0, 0])

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
        self.assertEqual(result[self.ta_ts_id]["data"].df['temperature_INFILL_FLAG'].to_list(), [0, 0, 2, 2, 0, 0, 1, 0, 0, 0])
