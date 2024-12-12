import unittest
from datetime import datetime
from unittest.mock import Mock, patch

import polars as pl
from polars.testing import assert_frame_equal

from dritimeseriesprocessor.quality_control.quality_controller import remove_qcd_data, run_quality_control
from time_series import TimeSeries, Period


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

    @patch("dritimeseriesprocessor.quality_control.quality_controller.get_qc_config")
    def test_preprocess_unimplemented_method(self, mock_get_qc_config):
        """ Test that run qc skips unimplemented methods.
        """
        mock_get_qc_config.return_value = {"unknown_check": Mock()}

        with self.assertLogs("dritimeseriesprocessor.quality_control.quality_controller", level="WARNING") as logs:
            result = run_quality_control(self.ts)
            print(logs.output[0])
            self.assertIn("Unimplemented method: unknown_check", logs.output[0])

        assert_frame_equal(result.df, self.ts.df)

    @patch("dritimeseriesprocessor.quality_control.quality_controller.get_qc_config")
    def test_qc_variable_not_in_df(self, mock_get_qc_config):
        """ Test that run qc skips corrections if the variable is not in DataFrame.
        """
        mock_get_qc_config.return_value = {"RANGE": Mock(
            variables=["non_existent_column"]
        )}

        with self.assertLogs("dritimeseriesprocessor.quality_control.quality_controller", level="WARNING") as logs:
            result = run_quality_control(self.ts)
            self.assertIn("Column non_existent_column not in DataFrame for method RANGE", logs.output[0])

        assert_frame_equal(result.df, self.ts.df)
