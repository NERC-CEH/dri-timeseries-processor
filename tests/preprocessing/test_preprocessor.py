import unittest
from datetime import datetime
from unittest.mock import patch

import polars as pl
from polars.testing import assert_frame_equal

from dritimeseriesprocessor.__metadata__.config_preprocessing import Correction
from dritimeseriesprocessor.preprocessing.preprocessor import preprocess


class TestPreprocess(unittest.TestCase):
    def setUp(self):
        self.df = pl.DataFrame({
            "SITE_ID": ["site1", "site1", "site2", "site3"],
            "time": [
                datetime(2023, 8, 10),
                datetime(2023, 8, 11),
                datetime(2023, 8, 12),
                datetime(2023, 8, 13)
            ],
            "value": [10, 20, 30, 40]
        })

        self.correction_config = Correction(
            VARIABLE="value",
            CORRECTION_FACTOR=2.0,
            SITE_ID="site1",
            START_DATETIME=datetime(2023, 8, 10),
            END_DATETIME=datetime(2023, 8, 12),
            METHOD_ID="MULTIPLY",
            DESCRIPTION="Testing"
        )

    @patch("dritimeseriesprocessor.preprocessing.preprocessor.preprocessing_config")
    def test_preprocess_unimplemented_method(self, mock_preprocessing_config):
        """Test that preprocess skips unimplemented methods.
        """
        self.correction_config.METHOD_ID = "unknown_method"
        mock_preprocessing_config.corrections = [self.correction_config]

        with self.assertLogs("dritimeseriesprocessor.preprocessing.preprocessor", level="WARNING") as logs:
            result = preprocess(self.df)
            print(logs.output[0])
            self.assertIn("Unimplemented method: unknown_method", logs.output[0])

        assert_frame_equal(result, self.df)

    @patch("dritimeseriesprocessor.preprocessing.preprocessor.preprocessing_config")
    def test_preprocess_variable_not_in_df(self, mock_preprocessing_config):
        """Test that preprocess skips corrections if the variable is not in DataFrame.
        """
        self.correction_config.VARIABLE = "non_existent_column"
        mock_preprocessing_config.corrections = [self.correction_config]

        with self.assertLogs("dritimeseriesprocessor.preprocessing.preprocessor", level="WARNING") as logs:
            result = preprocess(self.df)
            self.assertIn("Variable not in DataFrame: non_existent_column", logs.output[0])

        assert_frame_equal(result, self.df)
