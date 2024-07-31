import unittest
from unittest.mock import mock_open, patch

from dritimeseriesprocessor import filter_config_validation


class TestConfigFilterValidation(unittest.TestCase):
    def test_invalid_start_date(self):
        """Test exception raised for invalid start_date."""
        filter_config = """{
                            "datasets": [
                                {
                                "type": "LEVEL_-1_PRECIP_1MIN_2024_LOOPED",
                                "range": ["01/17/2024", "2024-01-18"]
                                }
                            ]
                        }"""

        with patch('builtins.open', mock_open(read_data=filter_config)) as file_mock:
            with self.assertRaises(ValueError):
                filter_config_validation.validate('some/path/to/filter_config')

    def test_invalid_end_date(self):
        """Test exception raised for invalid end_date."""
        filter_config = """{
                            "datasets": [
                                {
                                "type": "LEVEL_-1_PRECIP_1MIN_2024_LOOPED",
                                "range": ["2024-01-18", "01-18-2024"]
                                }
                            ]
                        }"""

        with patch('builtins.open', mock_open(read_data=filter_config)) as file_mock:
            with self.assertRaises(ValueError):
                filter_config_validation.validate('some/path/to/filter_config')

    def test_start_date_after_end_date(self):
        """Test exception raised for start_date after end_date."""
        filter_config = """{
                            "datasets": [
                                {
                                "type": "LEVEL_-1_PRECIP_1MIN_2024_LOOPED",
                                "range": ["2024-01-18", "2024-01-15"]
                                }
                            ]
                        }"""

        with patch('builtins.open', mock_open(read_data=filter_config)) as file_mock:
            with self.assertRaises(ValueError):
                filter_config_validation.validate('some/path/to/filter_config')

    def test_incorrect_data_type(self):
        """Test exception raised for incorrect type."""
        filter_config = """{
                            "datasets": [
                                {
                                "type": "WRONGWRONGWRONG",
                                "range": ["2024-01-18", "2024-01-15"]
                                }
                            ]
                        }"""

        with patch('builtins.open', mock_open(read_data=filter_config)) as file_mock:
            with self.assertRaises(ValueError):
                filter_config_validation.validate('some/path/to/filter_config')


    def test_columns_is_list(self):
        """Test column name filters are a list."""
        filter_config = """{
                            "datasets": [
                                {
                                "type": "WRONGWRONGWRONG",
                                "range": ["2024-01-18", "2024-01-15"],
                                "columns: ('a', 'b')
                                }
                            ]
                        }"""

        with patch('builtins.open', mock_open(read_data=filter_config)) as file_mock:
            with self.assertRaises(ValueError):
                filter_config_validation.validate('some/path/to/filter_config')