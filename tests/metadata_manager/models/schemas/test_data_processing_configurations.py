import unittest
from datetime import datetime
from itertools import product
from parameterized import parameterized
from unittest.mock import patch, MagicMock

from metadata_manager.models.schemas.data_processing_configurations import (
    Annotation,
    Parameter,
    ConfigItem,
    DataProcessingConfiguration,
    DataProcessingConfigurations
)


class TestAnnotation(unittest.TestCase):
    @parameterized.expand([
        (
                "test_int",
                {
                    "property": {"@id": "http://example.com/property/int_value"},
                    "hasValue": {"value": 10}
                },
                "int_value",
                10
        ),
        (
                "test_str",
                {
                    "property": {"@id": "http://example.com/property/str_value"},
                    "hasValue": {"value": "example"}
                },
                "str_value",
                "example"
        ),
        (
                "test_float",
                {
                    "property": {"@id": "http://example.com/property/float_value"},
                    "hasValue": {"value": 0.75}
                },
                "float_value",
                0.75
        ),
        (
                "test_none",
                {
                    "property": {"@id": "http://example.com/property/none_value"},
                    "hasValue": {"value": None}
                },
                "none_value",
                None
        ),
    ])
    def test_extract_param_info_success(self, _, test_data, expected_name, expected_value):
        """Test that annotation parameters are correctly extracted for various valid inputs."""
        result = Annotation.model_validate(test_data)
        self.assertEqual(result.name, expected_name)
        self.assertEqual(result.value, expected_value)

    def test_missing_property_id(self):
        """Test that validation fails when property @id is missing."""
        test_data = {
            "property": {},  # Missing @id
            "hasValue": {"value": 10}
        }
        with self.assertRaises(KeyError):
            Annotation.model_validate(test_data)

    def test_missing_property_field(self):
        """Test that validation fails when property field is missing."""
        test_data = {
            # Missing property field entirely
            "hasValue": {"value": 10}
        }
        with self.assertRaises(KeyError):
            Annotation.model_validate(test_data)

    def test_missing_value(self):
        """Test that validation fails when value is missing in hasValue."""
        # Arrange
        test_data = {
            "property": {"@id": "http://example.com/property/priority"},
            "hasValue": {}  # Missing value
        }
        with self.assertRaises(KeyError):
            Annotation.model_validate(test_data)

    def test_missing_has_value(self):
        """Test that validation fails when hasValue field is missing."""
        test_data = {
            "property": {"@id": "http://example.com/property/priority"}
            # Missing hasValue
        }
        with self.assertRaises(KeyError):
            Annotation.model_validate(test_data)


class TestParameter(unittest.TestCase):
    @parameterized.expand([
        ("test_int", 24),
        ("test_float", 0.75),
        ("test_str", "str_value"),
        ("test_none", None),
    ])
    def test_extract_param_info_with_direct_value(self, _, param_value):
        """Test parameter extraction with direct values of different types."""
        test_data = {
            "parameter": {"@id": "http://example.com/parameter/test_value"},
            "hasValue": {"value": param_value}
        }
        result = Parameter.model_validate(test_data)
        self.assertEqual(result.value, param_value)


    def test_extract_param_info_with_reference(self):
        """Test parameter extraction with reference values."""
        test_data = {
            "parameter": {"@id": "http://example.com/parameter/reference_value"},
            "hasValue": {"valueReference": {"@id": "http://example.com/variable/air_temp"}}
        }

        result = Parameter.model_validate(test_data)
        self.assertEqual(result.name, "reference_value")
        self.assertEqual(result.value, "http://example.com/variable/air_temp")

    @parameterized.expand([
        ("simple", "http://example.com/parameter/simple", "simple"),
        ("with_hyphen", "http://example.com/parameter/single-hyphen", "single_hyphen"),
        ("with_multiple_hyphen", "http://example.com/parameter/multiple-hyphen-test", "multiple_hyphen_test"),
        ("with_underscore", "http://example.com/parameter/under_score", "under_score"),
        ("with_multiple_underscore", "http://example.com/parameter/multiple_under_score", "multiple_under_score"),
        ("hypen_underscore", "http://example.com/parameter/mix-hyphen_underscore", "mix_hyphen_underscore")
    ])
    def test_parameter_name_parsing(self, _, id_value, expected):
        """ Test parameter names are parsed appropriately.
        Note that hyphens should get turned to underscores, so duplicating the regex tests from test_common.py
        but changing result to reflect this.
        """
        test_data = {
            "parameter": {"@id": id_value},
            "hasValue": {"value": 10}
        }
        result = Parameter.model_validate(test_data)
        self.assertEqual(result.name, expected)

    def test_missing_parameter_id(self):
        """Test that validation fails when parameter @id is missing."""        
        test_data = {
            "parameter": {},  # Missing @id
            "hasValue": {"value": 10}
        }
        with self.assertRaises(KeyError):
            Parameter.model_validate(test_data)

    def test_missing_parameter_field(self):
        """Test that validation fails when parameter field is missing."""
        test_data = {
            # Missing parameter field entirely
            "hasValue": {"value": 10}
        }
        with self.assertRaises(KeyError):
            Parameter.model_validate(test_data)

    def test_missing_has_value(self):
        """Test that validation fails when hasValue field is missing."""
        test_data = {
            "parameter": {"@id": "http://example.com/parameter/parameter_id"},
            # Missing hasValue
        }
        with self.assertRaises(KeyError):
            Parameter.model_validate(test_data)


class TestConfigItem(unittest.TestCase):
    """Test the ConfigItem model."""

    def test_extract_method_name(self):
        """Test extraction of method name from the @id field."""
        # Arrange
        test_data = {
            "method": {"@id": "http://example.com/method/linear-interpolation"},
        }
        result = ConfigItem.model_validate(test_data)
        self.assertEqual(result.name, "linear-interpolation")

    @parameterized.expand([
        (a, b, c, d) for (a, b), (c, d) in
        list(product(
            [("interval", "interval"), ("observationInterval", "observation_interval")],
            [
                ("2023-01-01T00:00:00", datetime(2023, 1, 1)),
                ("2023-06-15T12:30:45", datetime(2023, 6, 15, 12, 30, 45)),
                ("2023-12-31T23:59:59", datetime(2023, 12, 31, 23, 59, 59)),
            ]))
    ])
    def test_extract_interval_only_start(self, interval_name_in, interval_name_out, date_str, expected_datetime):
        """Test extraction of interval and observation interval that only includes a start date."""
        test_data = {
            "method": {"@id": "http://example.com/method/test"},
            interval_name_in: {"startDate": date_str},
        }
        result = ConfigItem.model_validate(test_data)
        self.assertEqual(getattr(result, interval_name_out), (expected_datetime, None))

    @parameterized.expand([
        (a, b, c, d) for (a, b), (c, d) in
        list(product(
            [("interval", "interval"), ("observationInterval", "observation_interval")],
            [
                ("2023-01-01T00:00:01", datetime(2023, 1, 1, 0, 0, 1)),
                ("2023-06-15T12:30:45", datetime(2023, 6, 15, 12, 30, 45)),
                ("2023-12-31T23:59:59", datetime(2023, 12, 31, 23, 59, 59)),
            ]))
    ])
    def test_extract_interval_only_end(self, interval_name_in, interval_name_out, date_str, expected_datetime):
        """Test extraction of interval and observation interval that only includes an end date."""
        test_data = {
            "method": {"@id": "http://example.com/method/test"},
            interval_name_in: {"endDate": date_str},
        }
        result = ConfigItem.model_validate(test_data)
        self.assertEqual(getattr(result, interval_name_out), (datetime(1800, 1, 1), expected_datetime))

    @parameterized.expand([
        (a, b, c, d, e) for (a, b), (c, d, e) in
        list(product(
            [("interval", "interval"), ("observationInterval", "observation_interval")],
            [
                ("2022-01-01", "2023-01-01", (datetime(2022, 1, 1), datetime(2023, 1, 1))),
                ("2022-01-01T00:00:01", "2023-06-15T12:30:45", (datetime(2022, 1, 1, 0, 0, 1), datetime(2023, 6, 15, 12, 30, 45))),
                ("2023-12-31T23:59:59", "2025-12-15", (datetime(2023, 12, 31, 23, 59, 59), datetime(2025, 12, 15))),
            ]))
    ])
    def test_extract_interval(self, interval_name_in, interval_name_out, start_date, end_date, expected):
        """Test extraction of interval and observation interval with start and end dates."""
        test_data = {
            "method": {"@id": "http://example.com/method/test"},
            interval_name_in: {
                "startDate": start_date,
                "endDate": end_date
            },
        }
        result = ConfigItem.model_validate(test_data)
        self.assertEqual(getattr(result, interval_name_out), expected)

    @parameterized.expand([
        (a, b, c) for a, (b, c) in
        list(product(
            ["interval", "observationInterval"],
            [
                ("2023-01-01", "2023-01-01"),
                ("2023-01-01", "2022-12-31"),
                ("2023-01-01T12:00:00", "2023-01-01T11:59:59")
            ]))
    ])
    def test_invalid_end_date(self, interval_name_in, start_date, end_date):
        """Test validation fails when end_date is not after start_date."""
        test_data = {
            "method": {"@id": "http://example.com/method/test"},
            interval_name_in: {
                "startDate": start_date,
                "endDate": end_date
            },
        }
        with self.assertRaises(ValueError):
            ConfigItem.model_validate(test_data)

    def test_extract_single_parameter(self):
        """Test extraction of a single parameter."""
        test_data = {
            "method": {"@id": "http://example.com/method/test"},
            "argument": [
                {
                    "parameter": {"@id": "http://example.com/parameter/max-gap"},
                    "hasValue": {"value": 6}
                }
            ]
        }
        result = ConfigItem.model_validate(test_data)
        self.assertEqual(len(result.parameters), 1)
        self.assertEqual(result.parameters["max_gap"], 6)

    def test_extract_multiple_parameters(self):
        """Test extraction of multiple parameters."""
        test_data = {
            "method": {"@id": "http://example.com/method/test"},
            "argument": [
                {
                    "parameter": {"@id": "http://example.com/parameter/max-gap"},
                    "hasValue": {"value": 6}
                },
                {
                    "parameter": {"@id": "http://example.com/parameter/window-size"},
                    "hasValue": {"value": 24}
                },
                {
                    "parameter": {"@id": "http://example.com/parameter/method-type"},
                    "hasValue": {"value": "linear"}
                }
            ]
        }
        result = ConfigItem.model_validate(test_data)
        self.assertEqual(len(result.parameters), 3)
        self.assertEqual(result.parameters["max_gap"], 6)
        self.assertEqual(result.parameters["window_size"], 24)
        self.assertEqual(result.parameters["method_type"], "linear")

    def test_extract_multiple_parameters_same_name(self):
        """Test multiple parameters with the same name should result in a list of values, not a single value."""
        test_data = {
            "method": {"@id": "http://example.com/method/test"},
            "argument": [
                {
                    "parameter": {"@id": "http://example.com/parameter/value"},
                    "hasValue": {"value": 6}
                },
                {
                    "parameter": {"@id": "http://example.com/parameter/value"},
                    "hasValue": {"value": 24}
                },
                {
                    "parameter": {"@id": "http://example.com/parameter/value"},
                    "hasValue": {"value": "linear"}
                }
            ]
        }
        result = ConfigItem.model_validate(test_data)
        self.assertEqual(len(result.parameters), 1)
        self.assertEqual(result.parameters["value"], [6, 24, "linear"])

    def test_missing_method_id(self):
        """Test that validation fails when method @id is missing."""
        test_data = {
            "method": {},  # Missing @id
        }
        with self.assertRaises(KeyError):
            ConfigItem.model_validate(test_data)

    def test_missing_observation_interval(self):
        """Test that validation passes when observationInterval is missing.
        It's okay for this to be missing, as we then assume it applies for the whole time series."""
        test_data = {
            "method": {"@id": "http://example.com/method/test"},
            # Missing observationInterval
        }
        ConfigItem.model_validate(test_data)

    def test_missing_start_date(self):
        """Test that validation passes when startDate is missing.
        It's okay for this to be missing, as we then assume it applies for the whole time series."""
        test_data = {
            "method": {"@id": "http://example.com/method/test"},
            "observationInterval": {},  # Missing startDate
        }
        ConfigItem.model_validate(test_data)


class TestDataProcessingConfiguration(unittest.TestCase):
    """Test the DataProcessingConfiguration model."""

    def setUp(self):
        self.test_data = {
            "appliesToTimeSeries": [{
                "@id": "http://example.com/id/dataset/example_name",
                "originatingSite": {"@id": "http://example.com/site/site-abcd1"}
            }],
            "hasAnnotation": [
                {
                    "property": {"@id": "http://example.com/property/data-processing-configuration-priority"},
                    "hasValue": {"value": 1}
                }
            ],
            "hasCurrentConfiguration": [
                {
                    "method": {"@id": "http://example.com/method/linear-interpolation"},
                    "observationInterval": {"startDate": "2023-01-01T00:00:00"},
                    "argument": [
                        {
                            "parameter": {"@id": "http://example.com/parameter/max-gap"},
                            "hasValue": {"value": 6}
                        }
                    ]
                }
            ]
        }


    def test_extract_site_id(self):
        """Test extraction of site ID."""
        result = DataProcessingConfiguration.model_validate(self.test_data)
        self.assertEqual(result.site_id, "http://example.com/site/site-abcd1")

    def test_extract_time_series_id(self):
        """Test extraction of time series name."""
        result = DataProcessingConfiguration.model_validate(self.test_data)
        self.assertEqual(result.ts_id, "http://example.com/id/dataset/example_name")

    @patch("metadata_manager.models.schemas.data_processing_configurations.ConfigItem.model_validate")
    def test_extract_method_config(self, mock_method_validate):
        """Test extraction and validation of method configuration."""
        mock_method = MagicMock(spec=ConfigItem)
        mock_method.name = "linear-interpolation"
        mock_method_validate.return_value = mock_method

        result = DataProcessingConfiguration.model_validate(self.test_data)
        self.assertEqual(result.configs, [mock_method])

    def test_extract_annotations(self):
        """Test extraction and validation of method configuration."""
        result = DataProcessingConfiguration.model_validate(self.test_data)
        self.assertEqual(result.annotations, {"data-processing-configuration-priority": 1})

    def test_missing_applies_to_time_series(self):
        """Test that validation fails when appliesToTimeSeries is missing."""
        test_data = self.test_data.copy()
        test_data.pop("appliesToTimeSeries")
        with self.assertRaises(KeyError):
            DataProcessingConfiguration.model_validate(test_data)

    def test_empty_applies_to_time_series(self):
        """Test that validation fails when appliesToTimeSeries is empty."""
        test_data = self.test_data.copy()
        test_data["appliesToTimeSeries"] = []
        with self.assertRaises(IndexError):
            DataProcessingConfiguration.model_validate(test_data)

    def test_missing_has_current_configuration(self):
        """Test that validation fails when hasCurrentConfiguration is missing."""
        test_data = self.test_data.copy()
        test_data.pop("hasCurrentConfiguration")
        with self.assertRaises(KeyError):
            DataProcessingConfiguration.model_validate(test_data)

    def test_empty_has_current_configuration(self):
        """Test that validation fails when hasCurrentConfiguration is empty."""
        test_data = self.test_data.copy()
        test_data["hasCurrentConfiguration"] = []
        with self.assertRaises(ValueError):
            DataProcessingConfiguration.model_validate(test_data)


class TestDataProcessingConfigurations(unittest.TestCase):
    @patch("metadata_manager.models.schemas.data_processing_configurations.DataProcessingConfiguration.model_validate")
    def test_model_validate_with_items_dict(self, mock_validate):
        """Test validation with a dictionary containing 'items'."""
        mock_config = MagicMock(spec=DataProcessingConfiguration)
        mock_validate.return_value = mock_config
        test_data = {
            "items": ["config1", "config2", "config3"]
        }

        result = DataProcessingConfigurations.model_validate(test_data)
        self.assertEqual(len(result), 3)

    @patch("metadata_manager.models.schemas.data_processing_configurations.DataProcessingConfiguration.model_validate")
    def test_model_validate_with_list(self, mock_validate):
        """Test validation with a list of items."""
        mock_config = MagicMock(spec=DataProcessingConfiguration)
        mock_validate.return_value = mock_config

        test_data = ["config1", "config2", "config3"]

        result = DataProcessingConfigurations.model_validate(test_data)
        self.assertEqual(len(result), 3)

    def test_model_validate_with_empty_dict_input(self):
        """Test validation with empty dict inputs."""
        result = DataProcessingConfigurations.model_validate({"items": []})
        self.assertEqual(len(result), 0)

    def test_model_validate_with_empty_list_input(self):
        """Test validation with empty list inputs."""
        result = DataProcessingConfigurations.model_validate([])
        self.assertEqual(len(result), 0)

    def test_model_validate_with_none(self):
        """ Test validation with None input."""
        result = DataProcessingConfigurations.model_validate(None)
        self.assertEqual(len(result), 0)

    def test_model_validate_with_dict_no_items(self):
        """ Test validation fails if dict input doesn't have an items key """
        with self.assertRaises(KeyError):
            DataProcessingConfigurations.model_validate({"not_items": []})
