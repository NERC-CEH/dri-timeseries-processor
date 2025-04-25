import unittest
from datetime import datetime
from unittest.mock import Mock, patch

import polars as pl
from polars.testing import assert_frame_equal

from dritimeseriesprocessor.quality_control.quality_controller import qc_flag_column_name, remove_qcd_data, run_quality_control
from time_stream import TimeSeries, Period



def mock_range_check(ts, column, flag_column):
    ts.add_flag(flag_column, "RANGE")
    return ts

def mock_spike_check(ts, column, flag_column):
    ts.add_flag(flag_column, "SPIKE")
    return ts

test_QC_CHECKS = {
    "RANGE": mock_range_check,
    "SPIKE": mock_spike_check,
}


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


# class TestRunQualityControlORIG(unittest.TestCase):
#     def setUp(self):
#         data = pl.DataFrame({
#             "time": [
#                 datetime(2023, 8, 10),
#                 datetime(2023, 8, 11),
#                 datetime(2023, 8, 12),
#                 datetime(2023, 8, 13),
#                 datetime(2023, 8, 14),
#                 datetime(2023, 8, 15)
#             ],
#             "value": [10., 20., 30., 40., 50., 60.]
#         })
#         resolution = Period.of_days(1)
#         periodicity = Period.of_days(1)
#         self.ts = TimeSeries(
#             data,
#             "time",
#             resolution,
#             periodicity
#         )




class TestRunQualityControl(unittest.TestCase):
    """
    Test suite for the run_quality_control function.
    """

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
        self.ts = TimeSeries(
            data,
            "time",
            resolution,
            periodicity
        )

        self.mock_qc_check_configs = {
            "RANGE": Mock(
                id=1,
                variables=["value"]
            ),
            "SPIKE": Mock(
                id=2,
                variables=["value"]
            ),
        }

    @patch("dritimeseriesprocessor.quality_control.quality_controller.get_qc_config")
    @patch('dritimeseriesprocessor.quality_control.quality_controller.QC_CHECKS', new=test_QC_CHECKS)
    def test_run_qc_basic(self, mock_get_qc_config):
        """
        Test basic functionality of run_quality_control.
        Checks if the function adds the flag system, adds the flag columns, and runs the infill methods.
        """
        mock_get_qc_config.return_value = self.mock_qc_check_configs

        result = run_quality_control(self.ts)

        # Check flag system added
        self.assertIn('qc_flags', result.flag_systems)
        # Check columns added
        self.assertIn('value_QC_FLAG', result.columns)
        # Check flag values (from mock functions) have been added
        self.assertEqual(result.df['value_QC_FLAG'].to_list(), [3, 3, 3, 3, 3, 3])

    @patch("dritimeseriesprocessor.quality_control.quality_controller.get_qc_config")
    def test_run_qc_no_config(self, mock_get_qc_config):
        """
        Test run_quality_control when no QC config is available.
        Checks if the function returns the original DataFrame unchanged.
        """
        mock_get_qc_config.return_value = {}

        result = run_quality_control(self.ts)

        assert_frame_equal(result.df, self.ts.df)

    @patch("dritimeseriesprocessor.quality_control.quality_controller.get_qc_config")
    def test_preprocess_unimplemented_method(self, mock_get_qc_config):
        """ Test that run qc skips unimplemented methods.
        """
        mock_get_qc_config.return_value = {"unknown_check": Mock(id=1)}

        with self.assertLogs("dritimeseriesprocessor.quality_control.quality_controller", level="WARNING") as logs:
            run_quality_control(self.ts)
            self.assertIn("Unimplemented QC check: unknown_check", logs.output[0])

    @patch("dritimeseriesprocessor.quality_control.quality_controller.get_qc_config")
    def test_qc_variable_not_in_df(self, mock_get_qc_config):
        """ Test that run qc skips corrections if the variable is not in DataFrame.
        """
        mock_get_qc_config.return_value = {"RANGE": Mock(
            id=1,
            variables=["non_existent_column"]
        )}

        with self.assertLogs("dritimeseriesprocessor.quality_control.quality_controller", level="WARNING") as logs:
            result = run_quality_control(self.ts)
            self.assertIn("Column non_existent_column not in DataFrame for method RANGE", logs.output[0])

        assert_frame_equal(result.df, self.ts.df)
