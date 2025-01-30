import unittest
from unittest.mock import Mock, patch

import polars as pl
from datetime import datetime
from parameterized import parameterized
from polars.testing import assert_frame_equal

from time_series import TimeSeries, Period
from dritimeseriesprocessor.__metadata__.config_quality_control import qc_tests
from dritimeseriesprocessor.quality_control.utils import (column_threshold_check, get_failed_qc_check_ids_from_flag,
                                                          get_site_range_values)


class TestColumnThresholdCheck(unittest.TestCase):
    def setUp(self):
        data = pl.DataFrame({
            'time': [
                datetime(2023, 8, 10),
                datetime(2023, 8, 11),
                datetime(2023, 8, 12),
                datetime(2023, 8, 13),
            ],
            "value_a": [5., 10., 20., 30.],
            "value_b": [1.0, 1.1, 1.2, 1.3],
            "value_c": [None, 50., 100., None],
        })

        resolution = Period.of_days(1)
        periodicity = Period.of_days(1)
        self.ts = TimeSeries(
            data,
            "time",
            resolution,
            periodicity
        )

        self.ts.add_flag_system("qc_flags", {
            "TEST": 1
        })
        self.ts.init_flag_column("qc_flags", "value_b_QC_FLAG")
        self.ts.init_flag_column("qc_flags", "value_c_QC_FLAG")

    def test_greater_than(self):
        """ Test the column threshold check function with '>' operator.
        """
        result = column_threshold_check(self.ts, "value_a", "value_b_QC_FLAG", 10, ">", 1)
        self.assertEqual(result.df['value_b_QC_FLAG'].to_list(), [0, 0, 1, 1])

    def test_greater_than_or_equal(self):
        """ Test the column threshold check function with '>=' operator.
        """
        result = column_threshold_check(self.ts, "value_a", "value_b_QC_FLAG", 10, ">=", 1)
        self.assertEqual(result.df['value_b_QC_FLAG'].to_list(), [0, 1, 1, 1])

    def test_less_than(self):
        """ Test the column threshold check function with '<' operator.
        """
        result = column_threshold_check(self.ts, "value_a", "value_b_QC_FLAG", 10, "<", 1)
        self.assertEqual(result.df['value_b_QC_FLAG'].to_list(), [1, 0, 0, 0])

    def test_less_than_or_equal(self):
        """ Test the column threshold check function with '<=' operator.
        """
        result = column_threshold_check(self.ts, "value_a", "value_b_QC_FLAG", 10, "<=", 1)
        self.assertEqual(result.df['value_b_QC_FLAG'].to_list(), [1, 1, 0, 0])
        
    def test_equal(self):
        """ Test the column threshold check function with '==' operator.
        """
        result = column_threshold_check(self.ts, "value_a", "value_b_QC_FLAG", 10, "==", 1)
        self.assertEqual(result.df['value_b_QC_FLAG'].to_list(), [0, 1, 0, 0])
        
    def test_not_equal(self):
        """ Test the column threshold check function with '!=' operator.
        """
        result = column_threshold_check(self.ts, "value_a", "value_b_QC_FLAG", 10, "!=", 1)
        self.assertEqual(result.df['value_b_QC_FLAG'].to_list(), [1, 0, 1, 1])

    def test_flag_na_when_true(self):
        """ Test that setting flag_na to True means that any NULL values in the check column are treated as failing
        the QC check (so qc flag set in result)
        """
        result = column_threshold_check(self.ts, "value_c", "value_b_QC_FLAG", 10, ">", 1, flag_na=True)
        self.assertEqual(result.df['value_b_QC_FLAG'].to_list(), [1, 1, 1, 1])

    def test_flag_na_when_false(self):
        """ Test that setting flag_na to False means that any NULL values in the check column are ignored in
        the QC check (so qc flag not set in result)
        """
        result = column_threshold_check(self.ts, "value_c", "value_b_QC_FLAG", 10, ">", 1, flag_na=False)
        self.assertEqual(result.df['value_b_QC_FLAG'].to_list(), [0, 1, 1, 0])

    def test_missing_check_column(self):
        """ Test that a missing check column raises error
        """
        with self.assertRaises(UserWarning):
            column_threshold_check(self.ts, "missing_check_column", "value_b_QC_FLAG", 10, ">", 1)

    def test_missing_flag_column(self):
        """ Test that a missing qc column raises error
        """
        with self.assertRaises(UserWarning):
            column_threshold_check(self.ts, "value_a", "missing_QC_FLAG", 10, ">", 1)

    def test_invalid_operator(self):
        """ Test that invalid operator raises error
        """
        with self.assertRaises(ValueError):
            column_threshold_check(self.ts, "value_a", "value_b_QC_FLAG", 10, ">>", 1)


class TestGetSiteRangeValues(unittest.TestCase):
    def setUp(self):
        self.range_thresholds = {
            "value": Mock(
                defaults=[
                    Mock(
                        min_value=1,
                        max_value=2,
                        resolutions=["PT1M"]
                    )
                ],
                sites=[
                    Mock(
                        site_id="site1",
                        min_value=10,
                        max_value=20,
                        resolutions=["PT1M", "PT15M"]
                    )
                ]
            ),

            "value2": Mock(
                defaults=[
                    Mock(
                        min_value=3,
                        max_value=4,
                        resolutions=None
                    )
                ],
                sites=[
                    Mock(
                        site_id="site1",
                        min_value=30,
                        max_value=40,
                        resolutions=None
                    )
                ]
            ),

            "value3": Mock(
                defaults=[
                    Mock(
                        min_value=99,
                        max_value=999,
                        resolutions=None
                    )
                ],
                sites=None
            )
        }

    @patch('dritimeseriesprocessor.quality_control.utils.get_qc_config')
    def test_get_site_specific_range_values(self, mock_get_qc_config):
        """ Test that we can get site specific range values for a given variable and resolution
        """
        mock_get_qc_config.return_value = self.range_thresholds
        result = get_site_range_values("site1", "value", "PT1M")
        expected = (10, 20)
        self.assertEqual(result, expected)

    @patch('dritimeseriesprocessor.quality_control.utils.get_qc_config')
    def test_get_site_specific_range_values_no_default(self, mock_get_qc_config):
        """ Test that we can get site specific range values for a given variable and resolution - even if that
        resolution doesn't exist in the defaults
        """
        mock_get_qc_config.return_value = self.range_thresholds
        result = get_site_range_values("site1", "value", "PT15M")
        expected = (10, 20)
        self.assertEqual(result, expected)

    @patch('dritimeseriesprocessor.quality_control.utils.get_qc_config')
    def test_get_site_specific_range_values_resolutions_none(self, mock_get_qc_config):
        """ Test that we can get site specific range values for a given variable and resolution when the resolutions
        parameter in the config is set to None (i.e. should apply to ALL resolutions)
        """
        mock_get_qc_config.return_value = self.range_thresholds
        result = get_site_range_values("site1", "value2", "PT30M")
        expected = (30, 40)
        self.assertEqual(result, expected)

    @patch('dritimeseriesprocessor.quality_control.utils.get_qc_config')
    def test_get_default_range_values(self, mock_get_qc_config):
        """ Test that we can get default range values for a given variable and resolution if site specific data
        doesn't exist
        """
        mock_get_qc_config.return_value = self.range_thresholds
        result = get_site_range_values("site_non_existent", "value", "PT1M")
        expected = (1, 2)
        self.assertEqual(result, expected)

    @patch('dritimeseriesprocessor.quality_control.utils.get_qc_config')
    def test_get_default_range_values_resolutions_none(self, mock_get_qc_config):
        """ Test that we can get default range values for a given variable and resolution if site specific data
        doesn't exist, and when the resolutions parameter in the config is set to None (i.e. should apply to ALL
        resolutions)
        """
        mock_get_qc_config.return_value = self.range_thresholds
        result = get_site_range_values("site_non_existent", "value2", "PT30M")
        expected = (3, 4)
        self.assertEqual(result, expected)

    @patch('dritimeseriesprocessor.quality_control.utils.get_qc_config')
    def test_no_variable(self, mock_get_qc_config):
        """ Test that an error raised if variable not in config
        """
        mock_get_qc_config.return_value = self.range_thresholds
        with self.assertRaises(UserWarning):
            get_site_range_values("site1", "value_non_existent", "PT1M")

    @patch('dritimeseriesprocessor.quality_control.utils.get_qc_config')
    def test_no_site_no_default(self, mock_get_qc_config):
        """ Test that an error raised if there is no site specific range values for a given variable and resolution,
        but also no default values to fall back on
        """
        mock_get_qc_config.return_value = self.range_thresholds
        with self.assertRaises(ValueError):
            get_site_range_values("site1", "value", "PT30M")

    @patch('dritimeseriesprocessor.quality_control.utils.get_qc_config')
    def test_no_sites_in_config(self, mock_get_qc_config):
        """ Test that default values returned if no site specific thresholds in the config
        """
        mock_get_qc_config.return_value = self.range_thresholds

        result = get_site_range_values("site1", "value3", "PT30M")
        expected = (99, 999)
        self.assertEqual(result, expected)


class TestQCFlagging(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Set up the test environment by mocking the global variables used in get_qc_config.
        This method is called before each test method.
        """
        # Mock the global variables used in the function
        mock_qc_tests = {
            "RANGE": {
                "id": 1 << 0
            },
            "MIN": {
                "id": 1 << 1
            },
            "MAX": {
                "id": 1 << 2
            }
        }

        cls.patcher = patch("dritimeseriesprocessor.__metadata__.config_quality_control.qc_tests", mock_qc_tests)
        cls.patcher.start()

    @classmethod
    def tearDownClass(cls):
        cls.patcher.stop()

    @parameterized.expand([
        [0, []],
        [1, [1]],
        [2, [2]],
        [4, [4]],
        [3, [1, 2]],
        [5, [1, 4]],
        [6, [2, 4]],
        [7, [1, 2, 4]],
        [64, [64]]
    ])
    def test_flag_is_reversible(self, flag, expected):
        """Checks that flags can be reversed into QC check IDs"""

        result = get_failed_qc_check_ids_from_flag(flag)

        self.assertListEqual(result, expected)
