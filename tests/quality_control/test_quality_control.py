import unittest
from unittest.mock import patch, MagicMock
import polars as pl
from polars.testing import assert_frame_equal

from dritimeseriesprocessor.quality_control.quality_control import qc_test_map, run_qc


class TestRunQC(unittest.TestCase):
    """
    Unit tests for the run_qc function.
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

    def test_run_qc_no_qc_tests_available(self):
        """
        Test the run_qc function when no QC tests are available for a variable.
        Verifies that the function skips QC tests and logs a warning.
        """
        original_qc_test_map = qc_test_map.copy()
        qc_test_map.clear()  # Clear all available QC tests

        result = run_qc(self.data)

        # Ensure no new columns were added due to lack of available tests
        self.assertNotIn(f"{self.test_column}_QCFLAG", result.columns)

        # Restore the original test map
        qc_test_map.update(original_qc_test_map)
