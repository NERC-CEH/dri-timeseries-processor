import unittest
from datetime import datetime
from unittest.mock import Mock, patch
import polars as pl

from time_stream import TimeSeries, Period
from dritimeseriesprocessor.flagging.flagger import add_initial_core_flags
from dritimeseriesprocessor.correcting.correcter import run_corrections

# Define mock mock functions
def mock_add_check(df: pl.DataFrame, column: str, correction_factor: float, mask: pl.Expr = pl.lit(True), *args, **kwargs):
    def _add() -> pl.Expr:
        return pl.col(column).add(correction_factor)

    corrected = df.with_columns(pl.when(mask).then(_add()).otherwise(pl.col(column)).alias(column))

    return corrected

def mock_multiply_check(df: pl.DataFrame, column: str, correction_factor: float, mask: pl.Expr = pl.lit(True), *args, **kwargs):
    def _multiply() -> pl.Expr:
        return pl.col(column).mul(correction_factor)

    corrected = df.with_columns(
        pl.when(mask).then(_multiply()).otherwise(pl.col(column)).alias(column),
    )

    return corrected


class TestRunCorrections(unittest.TestCase):
    """
    Test suite for the run_corrections function.
    """

    def setUp(self):
        """
        Set up common test data and mocks.
        """
        ta_data = pl.DataFrame({
            'time': [
                datetime(2023, 8, 10),
                datetime(2023, 8, 11),
                datetime(2023, 8, 12),
                datetime(2023, 8, 13),
                datetime(2023, 8, 14),
            ],
            'temperature': [20.0, 22.0, 21.0, 20.0, 19.0]
        })
        rh_data = pl.DataFrame({
            'time': [
                datetime(2023, 8, 10),
                datetime(2023, 8, 11),
                datetime(2023, 8, 12),
                datetime(2023, 8, 13),
                datetime(2023, 8, 14),
            ],
            'humidity': [50, 55, None, None, 60]
        })

        resolution = Period.of_days(1)
        periodicity = Period.of_days(1)

        ta_ts = TimeSeries(
            ta_data,
            "time",
            resolution,
            periodicity,
            metadata={"site_id": "site1", "column_name": "temperature"}
        )
        ta_ts = add_initial_core_flags(ta_ts)

        rh_ts = TimeSeries(
            rh_data,
            "time",
            resolution,
            periodicity,
            metadata={"site_id": "site1", "column_name": "humidity"}
        )
        rh_ts = add_initial_core_flags(rh_ts)

        self.ta_ts_id = "site1_temperature_1d_raw"
        self.rh_ts_id = "site1_humidity_1d_raw"

        self.ts_ids = {
            self.ta_ts_id: {
                "data": ta_ts,
            },
            self.rh_ts_id: {
                "data": rh_ts,
            }
        }

        # Set up dummy correction methods
        add = type("DummyCorrectionMethod", (), {
            "method_id": 1,
            "name": "ADD",
            "description": "Sum the data point and correction value",
            "function_name": "mock_add_check",
            "method_type": "correction",
            "__call__": lambda self, *args, **kwargs: mock_add_check(*args, **kwargs),
        })()

        multiply = type("DummyCorrectionMethod", (), {
            "method_id": 2,
            "name": "MULTIPLY",
            "description": "Multiply the data point by a correction factor",
            "function_name": "mock_multiply_check",
            "method_type": "correction",
            "__call__": lambda self, *args, **kwargs: mock_multiply_check(*args, **kwargs),
        })()

        self.mock_methods_dict = {
            "add_check": add,
            "multiply_check": multiply,
        }

        # Set up dummy correction configs
        self.correction_config1 = type("DummyCorrectionConfig", (), {
            "site_id": "site1",
            "ts_id": self.ta_ts_id,
            "configs": [type("DummyMethodConfig", (), {
                "name": "add_check",
                "interval": (datetime(2023, 8, 11), None),
                "observation_interval": (datetime(2023, 8, 11), datetime(2023, 8, 13)),
                "parameters": {'correction_factor': 10},
            })]
        })()

        self.correction_config2 = type("DummyCorrectionConfig", (), {
            "site_id": "site1",
            "ts_id": self.rh_ts_id,
            "configs": [type("DummyMethodConfig", (), {
                "name": "multiply_check",
                "interval": (datetime(2023, 8, 10), None),
                "observation_interval": (datetime(2023, 8, 10), datetime(2023, 8, 12)),
                "parameters": {'correction_factor': 2},
            })]
        })()


    @patch('dritimeseriesprocessor.correcting.correcter.load_config')
    @patch('dritimeseriesprocessor.correcting.correcter.get_correction_methods')
    def test_run_corrections_basic(self, mock_get_methods, mock_get_configs):
        """
        Test basic functionality of run_corrections.
        Checks if the function adds the flag system, adds the flag columns, and runs the correction method.
        """
        mock_get_configs.return_value = [self.correction_config1]
        mock_get_methods.return_value = self.mock_methods_dict
        
        result = run_corrections(self.ts_ids)

        # Check flag system added
        self.assertIn('corrs_flags', result[self.ta_ts_id]["data"].flag_systems)
        # Check columns added
        self.assertIn('temperature_CORRS_FLAG', result[self.ta_ts_id]["data"].columns)
        # Check the correction method has been applied
        self.assertEqual(result[self.ta_ts_id]["data"].df['temperature'].to_list(), [20.0, 32.0, 31.0, 30.0, 19.0])
        # Check CORRS flag values have been added
        self.assertEqual(result[self.ta_ts_id]["data"].df['temperature_CORRS_FLAG'].to_list(), [0, 1, 1, 1, 0])
        # Check core flag values updated
        self.assertEqual(result[self.ta_ts_id]["data"].df['temperature_CORE_FLAG'].to_list(), [32, 33, 33, 33, 32])


    @patch('dritimeseriesprocessor.correcting.correcter.load_config')
    @patch('dritimeseriesprocessor.correcting.correcter.get_correction_methods')
    def test_run_corrections_no_config(self, mock_get_methods, mock_get_configs):
        """
        Test run_corrections when no corrections config is available.
        Checks if the function returns the original DataFrame unchanged.
        """
        mock_get_configs.return_value = [self.correction_config1]
        mock_get_methods.return_value = self.mock_methods_dict

        result = run_corrections(self.ts_ids)

        self.assertEqual(result, self.ts_ids)


    @patch('dritimeseriesprocessor.correcting.correcter.load_config')
    @patch('dritimeseriesprocessor.correcting.correcter.get_correction_methods')
    def test_run_corrections_no_methods(self, mock_get_methods, mock_get_configs):
        """
        Test run_corrections when corrections config exists but no methods are specified.
        Checks if the function returns the original DataFrame unchanged.
        """
        mock_get_configs.return_value = [self.correction_config1]
        mock_get_methods.return_value = {}

        result = run_corrections(self.ts_ids)

        self.assertEqual(result, self.ts_ids)


    @patch('dritimeseriesprocessor.correcting.correcter.load_config')
    @patch('dritimeseriesprocessor.correcting.correcter.get_correction_methods')
    def test_run_corrections_multiple_methods(self, mock_get_methods, mock_get_configs):
        """
        Test run_corrections with multiple corrections methods for a single column.
        Checks if the method flags are all applied.
        """
        mock_get_configs.return_value = [self.correction_config1, self.correction_config2]
        mock_get_methods.return_value = self.mock_methods_dict

        result = run_corrections(self.ts_ids)

        # Check the correction method has been applied
        self.assertEqual(result[self.ta_ts_id]["data"].df['temperature'].to_list(), [40.0, 64.0, 62.0, 30.0, 19.0])
        self.assertEqual(result[self.rh_ts_id]["data"].df['humidity'].to_list(), [100, 130, None, None, 60])

        # Check core flags updated
        self.assertEqual(result[self.ta_ts_id]["data"].df['temperature_CORE_FLAG'].to_list(), [33, 33, 33, 33, 32])
        self.assertEqual(result[self.rh_ts_id]["data"].df['humidity_CORE_FLAG'].to_list(), [33, 33, 36, 36, 32])

        # Check CORRS flags updated
        self.assertEqual(result[self.ta_ts_id]["data"].df['temperature_CORRS_FLAG'].to_list(), [2, 3, 3, 1, 0])
        self.assertEqual(result[self.rh_ts_id]["data"].df['humidity_CORRS_FLAG'].to_list(), [2, 3, 0, 0, 0])


    @patch('dritimeseriesprocessor.correcting.correcter.load_config')
    @patch('dritimeseriesprocessor.correcting.correcter.get_correction_methods')
    def test_run_corrections_end_date_is_none(self, mock_get_methods, mock_get_configs):
        """
        Test end_date is None in config leads to all dates after start date being corrected.

        """
        self.correction_config1.configs[0].observation_interval = (datetime(2023, 8, 11), None)
        mock_get_configs.return_value = [self.correction_config1]
        mock_get_methods.return_value = self.mock_methods_dict

        result = run_corrections(self.ts_ids)

        # Check the correction method has been applied
        self.assertEqual(result[self.ta_ts_id]["data"].df['temperature'].to_list(), [20.0, 32.0, 31.0, 30.0, 29.0])
        # Check CORRS flag values have been added
        self.assertEqual(result[self.ta_ts_id]["data"].df['temperature_CORRS_FLAG'].to_list(), [0, 1, 1, 1, 1])
        # Check CORE flag values have been added
        self.assertEqual(result[self.ta_ts_id]["data"].df['temperature_CORE_FLAG'].to_list(), [32, 33, 33, 33, 33])
