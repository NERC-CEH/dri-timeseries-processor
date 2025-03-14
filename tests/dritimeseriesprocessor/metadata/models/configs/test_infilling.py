import unittest
from datetime import datetime
from parameterized import parameterized
from unittest.mock import patch, MagicMock

from dritimeseriesprocessor.metadata.models.configs.infilling import (
    Annotation,
    Parameter,
    MethodConfigItem,
    InfillingConfig,
    InfillingProcessConfigs
)
from dritimeseriesprocessor.metadata.models.time_series import TimeSeriesMetadata


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


class TestMethodConfigItem(unittest.TestCase):
    """Test the MethodConfigItem model."""

    def test_extract_method_name(self):
        """Test extraction of method name from the @id field."""
        # Arrange
        test_data = {
            "method": {"@id": "http://example.com/method/linear-interpolation"},
            "observationInterval": {"startDate": "2023-01-01T00:00:00"},
            "argument": []
        }
        result = MethodConfigItem.model_validate(test_data)
        self.assertEqual(result.name, "linear-interpolation")

    @parameterized.expand([
        ("2023-01-01T00:00:00", datetime(2023, 1, 1)),
        ("2023-06-15T12:30:45", datetime(2023, 6, 15, 12, 30, 45)),
        ("2023-12-31T23:59:59", datetime(2023, 12, 31, 23, 59, 59)),
    ])
    def test_extract_start_date(self, date_str, expected_datetime):
        """Test extraction of start date."""
        test_data = {
            "method": {"@id": "http://example.com/method/test"},
            "observationInterval": {"startDate": date_str},
            "argument": []
        }
        result = MethodConfigItem.model_validate(test_data)
        self.assertEqual(result.start_date, expected_datetime)

    @parameterized.expand([
        ("2023-01-01T00:00:01", datetime(2023, 1, 1, 0, 0, 1)),
        ("2023-06-15T12:30:45", datetime(2023, 6, 15, 12, 30, 45)),
        ("2023-12-31T23:59:59", datetime(2023, 12, 31, 23, 59, 59)),
    ])
    def test_extract_end_date(self, date_str, expected_datetime):
        """Test extraction of end date from observationInterval when present."""
        # Arrange
        test_data = {
            "method": {"@id": "http://example.com/method/test"},
            "observationInterval": {
                "startDate": "2023-01-01T00:00:00",
                "endDate": date_str
            },
            "argument": []
        }
        result = MethodConfigItem.model_validate(test_data)
        self.assertEqual(result.end_date, expected_datetime)

    def test_missing_end_date(self):
        """Test that end_date is None when not provided."""
        test_data = {
            "method": {"@id": "http://example.com/method/test"},
            "observationInterval": {"startDate": "2023-01-01T00:00:00"},
            "argument": []
        }
        result = MethodConfigItem.model_validate(test_data)
        self.assertIsNone(result.end_date)

    @parameterized.expand([
        ("same", "2023-01-01", "2023-01-01"),
        ("day_before", "2023-01-01", "2022-12-31"),
        ("second_before", "2023-01-01T12:00:00", "2023-01-01T11:59:59")
    ])
    def test_invalid_end_date(self, _, start_date, end_date):
        """Test validation fails when end_date is not after start_date."""
        test_data = {
            "method": {"@id": "http://example.com/method/test"},
            "observationInterval": {
                "startDate": start_date,
                "endDate": end_date
            },
            "argument": []
        }
        with self.assertRaises(ValueError):
            MethodConfigItem.model_validate(test_data)

    def test_extract_single_parameter(self):
        """Test extraction of a single parameter."""
        test_data = {
            "method": {"@id": "http://example.com/method/test"},
            "observationInterval": {"startDate": "2023-01-01T00:00:00"},
            "argument": [
                {
                    "parameter": {"@id": "http://example.com/parameter/max-gap"},
                    "hasValue": {"value": 6}
                }
            ]
        }
        result = MethodConfigItem.model_validate(test_data)
        self.assertEqual(len(result.parameters), 1)
        self.assertEqual(result.parameters["max_gap"], 6)

    def test_extract_multiple_parameters(self):
        """Test extraction of multiple parameters."""
        test_data = {
            "method": {"@id": "http://example.com/method/test"},
            "observationInterval": {"startDate": "2023-01-01T00:00:00"},
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
        result = MethodConfigItem.model_validate(test_data)
        self.assertEqual(len(result.parameters), 3)
        self.assertEqual(result.parameters["max_gap"], 6)
        self.assertEqual(result.parameters["window_size"], 24)
        self.assertEqual(result.parameters["method_type"], "linear")

    def test_missing_method_id(self):
        """Test that validation fails when method @id is missing."""
        test_data = {
            "method": {},  # Missing @id
            "observationInterval": {"startDate": "2023-01-01T00:00:00"},
            "argument": []
        }
        with self.assertRaises(KeyError):
            MethodConfigItem.model_validate(test_data)

    def test_missing_observation_interval(self):
        """Test that validation fails when observationInterval is missing."""
        test_data = {
            "method": {"@id": "http://example.com/method/test"},
            # Missing observationInterval
            "argument": []
        }
        with self.assertRaises(KeyError):
            MethodConfigItem.model_validate(test_data)

    def test_missing_start_date(self):
        """Test that validation fails when startDate is missing."""
        test_data = {
            "method": {"@id": "http://example.com/method/test"},
            "observationInterval": {},  # Missing startDate
            "argument": []
        }
        with self.assertRaises(KeyError):
            MethodConfigItem.model_validate(test_data)

    def test_missing_arguments(self):
        """Test handling when argument list is missing."""
        test_data = {
            "method": {"@id": "http://example.com/method/test"},
            "observationInterval": {"startDate": "2023-01-01T00:00:00"}
            # Missing argument
        }
        with self.assertRaises(KeyError):
            MethodConfigItem.model_validate(test_data)


class TestInfillingConfig(unittest.TestCase):
    """Test the InfillingConfig model."""

    def setUp(self):
        self.test_data = {
            "appliesToFacility": [{"@id": "http://example.com/facility/site-abcd1"}],
            "appliesToTimeSeries": [{"@id": "http://example.com/timeseries/air_temperature_hourly"}],
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
        # TODO: Decide how best to handle the API call that is done to get the timeseries variable info...
        #   I reckon it might be better not to extract that info in this config object.
        #   instead, just extract the variable name, and then externally do another API call to get the specific info.
        result = InfillingConfig.model_validate(self.test_data)
        self.assertEqual(result.site_id, "ABCD1")