import unittest
import polars as pl

from dritimeseriesprocessor.quality_control.utils import (
    add_qcflag_column,
    col_comparison_test,
    get_failed_qc_check_ids_from_flag,
    QCTestIDValidator,
)
from dritimeseriesprocessor.__metadata__.config_quality_control import qc_tests

from polars.testing import assert_frame_equal

from parameterized import parameterized
from unittest.mock import patch

class TestColComparison(unittest.TestCase):
    """
    Unit tests for the col_comparison function.
    """
    def setUp(self):
        """
        Set up the initial data for testing.
        This method is run before each test.
        """
        self.data = pl.DataFrame({
            "BATTV": [12.0, 11.5, 9.8, 10.2, 9.5],
            "TA": [20.0, 21.5, 22.1, 19.8, 18.0],
        })
        self.test_column = "TA"
        self.threshold = 10.0
        self.flag_value = 5

    def test_col_comparison_test_greater_than(self):
        """
        Test the col_comparison_test function with '>' operator.
        Verifies that the function correctly flags values greater than the threshold.
        """
        result = col_comparison_test(self.data, self.data["BATTV"], self.threshold, self.flag_value, op=">")
        expected_flags = [5, 5, 0, 5, 0]  # Expected flag results based on the data and threshold
        self.assertEqual(result[self.test_column].to_list(), expected_flags)

    def test_col_comparison_test_less_than(self):
        """
        Test the col_comparison_test function with '<' operator.
        Verifies that the function correctly flags values less than the threshold.
        """
        result = col_comparison_test(self.data, self.data["BATTV"], self.threshold, self.flag_value, op="<")
        expected_flags = [0, 0, 5, 0, 5]
        self.assertEqual(result[self.test_column].to_list(), expected_flags)

    def test_col_comparison_test_invalid_operator(self):
        """
        Test the col_comparison_test function with an invalid operator.
        Verifies that the function raises a ValueError.
        """
        with self.assertRaises(ValueError):
            col_comparison_test(self.data, self.data["BATTV"], self.threshold, self.flag_value, op="invalid_op")


class TestQCFlagging(unittest.TestCase):
    """Suite for testing the creation of QC flags."""

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


class TestAddQCFlagColumn(unittest.TestCase):
    """Test the add_qcflag_column function."""
    def setUp(self):
        """Set up the initial data for testing."""
        self.qc_flag = 1 << 5
        self.data = pl.DataFrame({
            "BATTV": [12.0, 11.5, 9.8, 10.2, 9.5],
            "TA": [20.0, 21.5, 22.1, 19.8, 18.0],
            "TA_QCFLAG": [0, 1, 3, 4, 0]
        })

        self.first_flag = pl.DataFrame({
            "BATTV": [0, 0, self.qc_flag, 0, self.qc_flag]
        })

        self.additional_flag = pl.DataFrame({
            "TA": [0, 0, self.qc_flag, 0 ,self.qc_flag]
        })


    def test_add_qcflag_column_first_flag(self):
        """Column failing QC checks for the first time."""
        expected = pl.DataFrame({
            "BATTV": [12.0, 11.5, 9.8, 10.2, 9.5],
            "TA": [20.0, 21.5, 22.1, 19.8, 18.0],
            "TA_QCFLAG": [0, 1, 3, 4, 0],
            "BATTV_QCFLAG": [0, 0, 32, 0, 32]
        })

        result = add_qcflag_column(self.data, self.first_flag, "BATTV")

        assert_frame_equal(result, expected)

    def test_add_qcflag_column_additional_flag(self):
        """Column failing QC checks a second time."""
        expected = pl.DataFrame({
            "BATTV": [12.0, 11.5, 9.8, 10.2, 9.5],
            "TA": [20.0, 21.5, 22.1, 19.8, 18.0],
            "TA_QCFLAG": [0, 1, 35, 4, 32],
        })

        result = add_qcflag_column(self.data, self.additional_flag, "TA")

        assert_frame_equal(result, expected)



if __name__ == "__main__":
    unittest.main()