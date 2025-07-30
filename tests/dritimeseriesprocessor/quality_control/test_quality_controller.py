import unittest
from datetime import datetime
from unittest.mock import patch, MagicMock
from typing import Any

import polars as pl
from polars.testing import assert_frame_equal

from dritimeseriesprocessor.flagging.flagger import add_initial_core_flags
from dritimeseriesprocessor.quality_control.quality_controller import remove_qcd_data, run_quality_control
from time_stream import TimeSeries, Period
from time_stream.qc import QCCheck


class MockCheck(QCCheck):
    name = "Mock"
    def __init__(self, **kwargs: Any):
        pass

    def expr(self, check_column: str) -> pl.Expr:
        return pl.lit(True)


class TestRemoveQCdData(unittest.TestCase):
    """ Unit tests for the remove_qcd_data function.
    """

    def test_remove_qcd_data(self):
        """
        Test that remove_qcd_data correctly removes QC'd data.
        """
        df = pl.DataFrame({
            'data': [1, 2, 3, 4, 5],
            'qc_flag': [0, 1, 0, 1, 0]
        })

        result = remove_qcd_data(df, 'data', 'qc_flag')
        expected = pl.DataFrame({
            'data': [1, None, 3, None, 5],
            'qc_flag': [0, 1, 0, 1, 0]
        })
        assert_frame_equal(result, expected)

    def test_no_qc_flags(self):
        """
        Test that remove_qcd_data returns the original dataframe when there are no QC flags.
        """
        df_no_flags = pl.DataFrame({
            'data': [1, 2, 3, 4, 5],
            'qc_flag': [0, 0, 0, 0, 0]
        })
        result = remove_qcd_data(df_no_flags, 'data', 'qc_flag')

        assert_frame_equal(result, df_no_flags)

    def test_all_qc_flags(self):
        """
        Test that remove_qcd_data returns a dataframe with all None values in the data column when all QC flags are set.
        """
        df_all_flags = pl.DataFrame({
            'data': [1, 2, 3, 4, 5],
            'qc_flag': [1, 1, 1, 1, 1]
        })
        result = remove_qcd_data(df_all_flags, 'data', 'qc_flag')
        expected = pl.DataFrame({
            'data': [None, None, None, None, None],
            'qc_flag': [1, 1, 1, 1, 1]
        }, schema={'data': pl.Int64, 'qc_flag': pl.Int64})

        assert_frame_equal(result, expected)


class TestRunQualityControl(unittest.TestCase):
    def setUp(self):
        """
        Set up common test data and mocks.
        """
        data = pl.DataFrame({
            "time": [
                datetime(2023, 8, 10),
                datetime(2023, 8, 11),
                datetime(2023, 8, 12),
                datetime(2023, 8, 13),
                datetime(2023, 8, 14),
                datetime(2023, 8, 15)
            ],
            "value": [10., 20., 30., 40., 50., 60.]
        })

        resolution = Period.of_days(1)
        periodicity = Period.of_days(1)
        ts = TimeSeries(data, "time", resolution, periodicity, metadata={"site_id": "SITE1", "column_name": "value"})
        ts = add_initial_core_flags(ts)

        self.ta_ts_id = "SITE1_ta_30min_raw"
        self.pa_ts_id = "SITE1_pa_30min_raw"

        site_id = "SITE1"
        self.ts_ids = {
            self.ta_ts_id: {
                "data": ts,
            },
            self.pa_ts_id: {
                "data": ts,
            }
        }

        # Set up dummy QC methods
        QC_method1 = type("DummyQCMethod", (), {
            "method_id": 1,
            "name": "Mock Check 1",
            "description": "A mock qc check",
            "function_name": MockCheck,
            "method_type": "quality_control",
            "arg_mapping": {},
            "arg_defaults": {}
        })()

        QC_method2 = type("DummyQCMethod", (), {
            "method_id": 2,
            "name": "Mock Check 2",
            "description": "Another mock qc check",
            "function_name": MockCheck,
            "method_type": "quality_control",
            "arg_mapping": {},
            "arg_defaults": {}
        })()

        QC_method3 = type("DummyQCMethod", (), {
            "method_id": 4,
            "name": "Mock Check 3",
            "description": "Another mock qc check",
            "function_name": MockCheck,
            "method_type": "quality_control",
            "arg_mapping": {},
            "arg_defaults": {}
        })()

        self.mock_methods_dict = {
            "mock_check1": QC_method1,
            "mock_check2": QC_method2,
            "mock_check3": QC_method3,
        }

        # Set up quality_control configs
        self.QC_config1 = type("DummyQCConfig", (), {
            "site_id": site_id,
            "ts_id": self.ta_ts_id,
            "configs": [type("DummyMethodConfig", (), {
                "name": "mock_check1",
                "interval": (datetime(2000, 1, 1), None),
                "observation_interval": (datetime(2023, 1, 1), None),
                "parameters": {
                    "arg1": -40,
                    "arg2": 40,
                },
            })],
            "annotations": {}
        })()

        self.QC_config2 = type("DummyQCConfig", (), {
            "site_id": site_id,
            "ts_id": self.pa_ts_id,
            "configs": [type("DummyMethodConfig", (), {
                "name": "mock_check2",
                "interval": (datetime(2000, 1, 1), None),
                "observation_interval": (datetime(2023, 1, 1), None),
                "parameters": {
                    "arg1": 20,
                    "arg2": 400,
                },
            })],
            "annotations": {}
        })()

        self.QC_config3 = type("DummyQCConfig", (), {
            "site_id": site_id,
            "ts_id": self.pa_ts_id,
            "configs": [type("DummyMethodConfig", (), {
                "name": "mock_check3",
                "interval": (datetime(2000, 1, 1), None),
                "observation_interval": (datetime(2023, 8, 11), datetime(2023, 8, 13)),
                "parameters": {
                    "arg1": 20,
                    "arg2": 400,
                },
            })],
            "annotations": {}
        })()

    @patch('dritimeseriesprocessor.quality_control.quality_controller.load_config')
    @patch('dritimeseriesprocessor.quality_control.quality_controller.get_qc_methods')
    def test_run_quality_control_no_methods(self, mock_get_methods, mock_get_configs):
        """Test run_quality_control when no QC methods are defined."""
        mock_get_configs.return_value = [MagicMock()]
        mock_get_methods.return_value = {}
        result = run_quality_control(self.ts_ids)

        self.assertEqual(result, self.ts_ids)

    @patch('dritimeseriesprocessor.quality_control.quality_controller.load_config')
    @patch('dritimeseriesprocessor.quality_control.quality_controller.get_qc_methods')
    def test_run_quality_control_success(self, mock_get_methods, mock_get_configs):
        """Test basic results of run_quality_control.
        """
        mock_get_configs.return_value = [self.QC_config1]
        mock_get_methods.return_value = self.mock_methods_dict

        # Call function
        result = run_quality_control(self.ts_ids)

        # Check flag system added
        self.assertIn('qc_flags', result[self.ta_ts_id]["data"].flag_systems)
        # Check columns added
        self.assertIn('value_QC_FLAG', result[self.ta_ts_id]["data"].columns)
        # Check flag values (from mock functions) have been added
        self.assertEqual(result[self.ta_ts_id]["data"].df['value_QC_FLAG'].to_list(), [1, 1, 1, 1, 1, 1])

    @patch('dritimeseriesprocessor.quality_control.quality_controller.load_config')
    @patch('dritimeseriesprocessor.quality_control.quality_controller.get_qc_methods')
    def test_run_quality_control_multiple_methods(self, mock_get_methods, mock_get_configs):
        """ Test run_quality_control with multiple QC methods for a single column.
        Checks if the methods are applied in the correct order (by priority).
        """
        mock_get_configs.return_value = [self.QC_config1, self.QC_config2]
        mock_get_methods.return_value = self.mock_methods_dict

        # Call function
        result = run_quality_control(self.ts_ids)

        # Check flag system added
        self.assertIn('qc_flags', result[self.ta_ts_id]["data"].flag_systems)
        # Check columns added
        self.assertIn('value_QC_FLAG', result[self.ta_ts_id]["data"].columns)
        # Check flag values (from both mock functions) have been added
        self.assertEqual(result[self.ta_ts_id]["data"].df['value_QC_FLAG'].to_list(), [3, 3, 3, 3, 3, 3])

    @patch('dritimeseriesprocessor.quality_control.quality_controller.load_config')
    @patch('dritimeseriesprocessor.quality_control.quality_controller.get_qc_methods')
    def test_run_quality_control_observation_interval(self, mock_get_methods, mock_get_configs):
        """ Test run_quality_control that has an observation interval - meaning that only data for a specific date
        range should be flagged
        """
        mock_get_configs.return_value = [self.QC_config3]
        mock_get_methods.return_value = self.mock_methods_dict

        # Call function
        result = run_quality_control(self.ts_ids)

        # Check flag system added
        self.assertIn('qc_flags', result[self.ta_ts_id]["data"].flag_systems)
        # Check columns added
        self.assertIn('value_QC_FLAG', result[self.ta_ts_id]["data"].columns)
        # Check flag values (from both mock functions) have been added
        self.assertEqual(result[self.ta_ts_id]["data"].df['value_QC_FLAG'].to_list(), [0, 4, 4, 4, 0, 0])
