import unittest
from unittest.mock import Mock, patch

import polars as pl
from polars.testing import assert_frame_equal

from dritimeseriesprocessor.__metadata__.config_quality_control import qc_tests
from dritimeseriesprocessor.quality_control.utils import (column_threshold_check, get_site_range_values,
                                                          initialise_qc_column, QCTestIDValidator)


class TestColumnThresholdCheck(unittest.TestCase):
    def setUp(self):
        self.data = pl.DataFrame({
            "value_a": [5., 10., 20., 30.],
            "value_b": [1.0, 1.1, 1.2, 1.3],
            "value_c": [None, 50., 100., None]
        })

    def test_greater_than(self):
        """ Test the column threshold check function with '>' operator.
        """
        result = column_threshold_check(self.data, "value_a", "value_b", 10, ">", 1)
        expected = self.data.with_columns(pl.Series("value_b_QCFLAG", [0, 0, 1, 1]))
        assert_frame_equal(result, expected)

    def test_greater_than_or_equal(self):
        """ Test the column threshold check function with '>=' operator.
        """
        result = column_threshold_check(self.data, "value_a", "value_b", 10, ">=", 1)
        expected = self.data.with_columns(pl.Series("value_b_QCFLAG", [0, 1, 1, 1]))
        assert_frame_equal(result, expected)

    def test_less_than(self):
        """ Test the column threshold check function with '<' operator.
        """
        result = column_threshold_check(self.data, "value_a", "value_b", 10, "<", 1)
        expected = self.data.with_columns(pl.Series("value_b_QCFLAG", [1, 0, 0, 0]))
        assert_frame_equal(result, expected)

    def test_less_than_or_equal(self):
        """ Test the column threshold check function with '<=' operator.
        """
        result = column_threshold_check(self.data, "value_a", "value_b", 10, "<=", 1)
        expected = self.data.with_columns(pl.Series("value_b_QCFLAG", [1, 1, 0, 0]))
        assert_frame_equal(result, expected)
        
    def test_equal(self):
        """ Test the column threshold check function with '==' operator.
        """
        result = column_threshold_check(self.data, "value_a", "value_b", 10, "==", 1)
        expected = self.data.with_columns(pl.Series("value_b_QCFLAG", [0, 1, 0, 0]))
        assert_frame_equal(result, expected)
        
    def test_not_equal(self):
        """ Test the column threshold check function with '!=' operator.
        """
        result = column_threshold_check(self.data, "value_a", "value_b", 10, "!=", 1)
        expected = self.data.with_columns(pl.Series("value_b_QCFLAG", [1, 0, 1, 1]))
        assert_frame_equal(result, expected)

    def test_flag_na_when_true(self):
        """ Test that setting flag_na to True means that any NULL values in the check column are treated as failing
        the QC check (so qc flag set in result)
        """
        result = column_threshold_check(self.data, "value_c", "value_b", 10, ">", 1, flag_na=True)
        expected = self.data.with_columns(pl.Series("value_b_QCFLAG", [1, 1, 1, 1]))
        assert_frame_equal(result, expected)

    def test_flag_na_when_false(self):
        """ Test that setting flag_na to False means that any NULL values in the check column are ignored in
        the QC check (so qc flag not set in result)
        """
        result = column_threshold_check(self.data, "value_c", "value_b", 10, ">", 1, flag_na=False)
        expected = self.data.with_columns(pl.Series("value_b_QCFLAG", [0, 1, 1, 0]))
        assert_frame_equal(result, expected)

    def test_missing_check_column(self):
        """ Test that a missing check column raises error
        """
        with self.assertRaises(UserWarning):
            column_threshold_check(self.data, "missing_check_column", "value_b", 10, ">", 1)

    def test_missing_qc_column(self):
        """ Test that a missing qc column raises error
        """
        with self.assertRaises(UserWarning):
            column_threshold_check(self.data, "value_a", "missing_qc_column", 10, ">", 1)

    def test_invalid_operator(self):
        """ Test that invalid operator raises error
        """
        with self.assertRaises(ValueError):
            column_threshold_check(self.data, "value_a", "value_b", 10, ">>", 1)


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


class TestInitialiseQcColumn(unittest.TestCase):
    def test_qc_column_not_exists(self):
        df = pl.DataFrame({"value": [1, 2, 3, 4]})
        result, qc_column = initialise_qc_column(df, "value")

        expected = pl.DataFrame({
            "value": [1, 2, 3, 4],
            "value_QCFLAG": [0, 0, 0, 0]
        })

        assert_frame_equal(result, expected)
        self.assertEqual(qc_column, "value_QCFLAG")

    def test_qc_column_already_exists(self):
        df = pl.DataFrame({
            "value": [1, 2, 3, 4],
            "value_QCFLAG": [1, 1, 1, 1]
        })
        result, qc_column = initialise_qc_column(df, "value")

        assert_frame_equal(result, df)
        self.assertEqual(qc_column, "value_QCFLAG")

    def test_empty_dataframe(self):
        df = pl.DataFrame({})
        with self.assertRaises(UserWarning):
            initialise_qc_column(df, "new_column")


class TestQCTestValidator(unittest.TestCase):
    """Suite to check validity of QC tests in codebase"""

    def setUp(self):
        self.good_tests = {
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

    def test_unique_ids(self):
        """Ensures that all tests have unique IDs"""

        self.assertTrue(
            QCTestIDValidator._ids_are_unique(self.good_tests)
        )

        non_unique_ids = {
            "RANGE": {
                "id": 1 << 0
            },
            "MIN": {
                "id": 1 << 0
            },
            "MAX": {
                "id": 1 << 2
            }
        }

        self.assertFalse(QCTestIDValidator._ids_are_unique(non_unique_ids))

    def test_bitwise_ids(self):
        """Ensures that all test_ids are bitwise (2**n)"""

        self.assertTrue(
            QCTestIDValidator._ids_are_bitwise(self.good_tests)
        )

        bad_tests_int = {
            "RANGE": {
                "id": 1 << 0
            },
            "MIN": {
                "id": 3
            },
            "MAX": {
                "id": 1 << 1
            }
        }

        bad_tests_float = {
            "RANGE": {
                "id": 1 << 0
            },
            "MIN": {
                "id": 1 << 1
            },
            "MAX": {
                "id": 1.5
            }
        }

        self.assertFalse(QCTestIDValidator._ids_are_bitwise(bad_tests_int))

        with self.assertRaises(TypeError):
            QCTestIDValidator._ids_are_bitwise(bad_tests_float)

    def test_sequential_ids(self):
        """Ensures that all tests have sequential IDs"""

        self.assertTrue(
            QCTestIDValidator._ids_are_sequential(self.good_tests)
        )

        bad_tests = {
            "RANGE": {
                "id": 1 << 1
            },
            "MIN": {
                "id": 1 << 0
            },
            "MAX": {
                "id": 1 << 2
            }
        }

        self.assertFalse(QCTestIDValidator._ids_are_sequential(bad_tests))

    def test_missing_test_id_returns_false(self):
        """Tests that a KeyError is raised if there is no test ID for a given test"""

        bad_tests = {
            "RANGE": {
                "id": 1 << 0
            },
            "MIN": {
                "id": 1 << 1
            },
            "MAX": {
            }
        }

        self.assertTrue(QCTestIDValidator._ids_are_all_present(self.good_tests))
        self.assertFalse(QCTestIDValidator._ids_are_all_present(bad_tests))


    @patch("dritimeseriesprocessor.quality_control.utils.QCTestIDValidator._ids_are_sequential")
    @patch("dritimeseriesprocessor.quality_control.utils.QCTestIDValidator._ids_are_bitwise")
    @patch("dritimeseriesprocessor.quality_control.utils.QCTestIDValidator._ids_are_unique")
    @patch("dritimeseriesprocessor.quality_control.utils.QCTestIDValidator._ids_are_all_present")
    def test_validation_methods_called(self, mock_checks_have_ids, mock_ids_are_unique, mock_ids_are_bitwise, mock_ids_are_sequential):
        """Tests that all validation methods are called when main function invoked"""

        assert QCTestIDValidator.validate(self.good_tests)
        assert mock_ids_are_unique.called
        assert mock_ids_are_bitwise.called
        assert mock_ids_are_sequential.called
        assert mock_checks_have_ids.called


class TestQCTestsAreValid(unittest.TestCase):

    def test_check_validity(self):
        """Runs the QCTestIDValidator"""

        invalid_msg = "QC tests in config are invalid."

        self.assertTrue(QCTestIDValidator._ids_are_all_present(qc_tests),
            msg=f"{invalid_msg} Some tests don't have IDs."
            )
        self.assertTrue(QCTestIDValidator._ids_are_bitwise(qc_tests),
            msg=f"{invalid_msg} Some tests are not bitwise."
            )
        self.assertTrue(QCTestIDValidator._ids_are_sequential(qc_tests),
            msg=f"{invalid_msg} Tests are not sequential."
            )
        self.assertTrue(QCTestIDValidator._ids_are_unique(qc_tests),
            msg=f"{invalid_msg} Some tests are not unique."
            )