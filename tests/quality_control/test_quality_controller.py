import unittest
from datetime import datetime
from unittest.mock import Mock, patch

import polars as pl
from polars.testing import assert_frame_equal

from dritimeseriesprocessor.quality_control.quality_controller import run_quality_control


class TestRunQualityControl(unittest.TestCase):
    def setUp(self):
        self.data = pl.DataFrame({
            "SITE_ID": ["site1", "site2", "site1", "site2", "site1", "site2"],
            "time": [
                datetime(2023, 8, 10),
                datetime(2023, 8, 10),
                datetime(2023, 8, 11),
                datetime(2023, 8, 11),
                datetime(2023, 8, 12),
                datetime(2023, 8, 12)
            ],
            "value": [10., 20., 30., 40., 50., 60.]
        })

    @patch("dritimeseriesprocessor.quality_control.quality_controller.get_qc_config")
    def test_preprocess_unimplemented_method(self, mock_get_qc_config):
        """ Test that run qc skips unimplemented methods.
        """
        mock_get_qc_config.return_value = {"unknown_check": Mock()}

        with self.assertLogs("dritimeseriesprocessor.quality_control.quality_controller", level="WARNING") as logs:
            result = run_quality_control(self.data)
            print(logs.output[0])
            self.assertIn("Unimplemented method: unknown_check", logs.output[0])

        assert_frame_equal(result, self.data)

    @patch("dritimeseriesprocessor.quality_control.quality_controller.get_qc_config")
    def test_qc_variable_not_in_df(self, mock_get_qc_config):
        """ Test that run qc skips corrections if the variable is not in DataFrame.
        """
        mock_get_qc_config.return_value = {"RANGE": Mock(
            variables=["non_existent_column"]
        )}

        with self.assertLogs("dritimeseriesprocessor.quality_control.quality_controller", level="WARNING") as logs:
            result = run_quality_control(self.data)
            self.assertIn("Variable non_existent_column not in DataFrame for method RANGE", logs.output[0])

        assert_frame_equal(result, self.data)


if __name__ == "__main__":
    unittest.main()
