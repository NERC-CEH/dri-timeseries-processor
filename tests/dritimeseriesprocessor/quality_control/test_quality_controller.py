import unittest
from datetime import datetime
from unittest.mock import patch, MagicMock

import polars as pl
from polars.testing import assert_frame_equal

from dritimeseriesprocessor.quality_control.quality_controller import qc_flag_column_name, remove_qcd_data, run_quality_control
from time_stream import TimeSeries, Period


def mock_range_check(ts, column, flag_column, flag_name, *args, **kwargs):
    ts.add_flag(flag_column, flag_name)
    return ts

def mock_spike_check(ts, column, flag_column, flag_name, *args, **kwargs):
    ts.add_flag(flag_column, flag_name)
    return ts


class TestQCFlagColumnName(unittest.TestCase):
    """Unit tests for the qc_flag_column_name function.
    """
    def test_standard_column_name(self):
        """
        Test that the function correctly appends '_QC_FLAG' to a standard column name.
        """
        self.assertEqual(qc_flag_column_name('data'), 'data_QC_FLAG')


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
        self.ts = TimeSeries(data, "time", resolution, periodicity)

        self.ts_ids = ["ta_30min_raw", "pa_30min_raw"]
        site_id = "SITE1"
        self.metadata = {
            "ta_30min_raw": {
                "sourceColumnName": "temperature",
            },
            "pa_30min_raw": {
                "sourceColumnName": "pressure",
            }
        }

        # Set up dummy QC methods
        QC_method1 = type("DummyQCMethod", (), {
            "method_id": 1,
            "name": "Range Check",
            "description": "Check if the value is within the specified range",
            "function_name": "mock_range_check",
            "method_type": "quality_control",
            "__call__": lambda self, *args, **kwargs: mock_range_check(*args, **kwargs),
        })()

        QC_method2 = type("DummyQCMethod", (), {
            "method_id": 2,
            "name": "Spike Check",
            "description": "Check if the value is a spike",
            "function_name": "mock_spike_check",
            "method_type": "quality_control",
            "__call__": lambda self, *args, **kwargs: mock_spike_check(*args, **kwargs),
        })()

        self.mock_methods_dict = {
            "range_check": QC_method1,
            "spike_check": QC_method2,
        }

        # Set up quality_control configs
        self.QC_config1 = type("DummyQCConfig", (), {
            "site_id": site_id,
            "ts_id": self.ts_ids[0],
            "configs": [type("DummyMethodConfig", (), {
                "name": "range_check",
                "interval": (datetime(2000, 1, 1), None),
                "observation_interval": (datetime(2023, 1, 1), None),
                "parameters": {
                    "lt": -40,
                    "gt": 40,
                },
            })],
            "annotations": {}
        })()

        self.QC_config2 = type("DummyQCConfig", (), {
            "site_id": site_id,
            "ts_id": self.ts_ids[1],
            "configs": [type("DummyMethodConfig", (), {
                "name": "spike_check",
                "interval": (datetime(2000, 1, 1), None),
                "observation_interval": (datetime(2023, 1, 1), None),
                "parameters": {
                    "gt": 20
                },
            })],
            "annotations": {}
        })()

    @patch('dritimeseriesprocessor.quality_control.quality_controller.load_config')
    def test_run_quality_control_no_configs(self, mock_get_configs):
        """Test run_quality_control when no configs are found for a ts_id."""
        ts_ids = ["NONEXISTENT"]

        mock_get_configs.return_value = []
        with self.assertRaises(KeyError):
            run_quality_control(self.ts, ts_ids, self.metadata)

    @patch('dritimeseriesprocessor.quality_control.quality_controller.load_config')
    @patch('dritimeseriesprocessor.quality_control.quality_controller.get_qc_methods')
    def test_run_quality_control_no_methods(self, mock_get_methods, mock_get_configs):
        """Test run_quality_control when no QC methods are defined."""
        mock_get_configs.return_value = [MagicMock()]
        mock_get_methods.return_value = {}
        result = run_quality_control(self.ts, self.ts_ids, self.metadata)

        self.assertEqual(result, self.ts)

    @patch('dritimeseriesprocessor.quality_control.quality_controller.load_config')
    @patch('dritimeseriesprocessor.quality_control.quality_controller.get_qc_methods')
    def test_run_quality_control_success(self, mock_get_methods, mock_get_configs):
        """Test basic results of run_quality_control.
        """
        mock_get_configs.return_value = [self.QC_config1]
        mock_get_methods.return_value = self.mock_methods_dict

        # Call function
        result = run_quality_control(self.ts, self.ts_ids, self.metadata)

        # Check flag system added
        self.assertIn('qc_flags', result.flag_systems)
        # Check columns added
        self.assertIn('temperature_QC_FLAG', result.columns)
        # Check flag values (from mock functions) have been added
        self.assertEqual(result.df['temperature_QC_FLAG'].to_list(), [1, 1, 1, 1, 1, 1])

    @patch('dritimeseriesprocessor.quality_control.quality_controller.load_config')
    @patch('dritimeseriesprocessor.quality_control.quality_controller.get_qc_methods')
    def test_run_quality_control_multiple_methods(self, mock_get_methods, mock_get_configs):
        """ Test run_quality_control with multiple QC methods for a single column.
        Checks if the methods are applied in the correct order (by priority).
        """
        mock_get_configs.return_value = [self.QC_config1, self.QC_config2]
        mock_get_methods.return_value = self.mock_methods_dict

        # Call function
        result = run_quality_control(self.ts, self.ts_ids, self.metadata)

        # Check flag system added
        self.assertIn('qc_flags', result.flag_systems)
        # Check columns added
        self.assertIn('temperature_QC_FLAG', result.columns)
        # Check flag values (from both mock functions) have been added
        self.assertEqual(result.df['temperature_QC_FLAG'].to_list(), [3, 3, 3, 3, 3, 3])
