from datetime import datetime, time
from itertools import product
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest

from metadata_manager.models.schemas.data_processing_configurations import (
    Annotation,
    ConfigItem,
    DataProcessingConfiguration,
    DataProcessingConfigurations,
    Parameter,
)


class TestAnnotation:
    @pytest.mark.parametrize(
        "test_data,expected_name,expected_value",
        [
            (
                {"property": {"@id": "http://example.com/property/int_value"}, "hasValue": {"value": 10}},
                "int_value",
                10,
            ),
            (
                {"property": {"@id": "http://example.com/property/str_value"}, "hasValue": {"value": "example"}},
                "str_value",
                "example",
            ),
            (
                {"property": {"@id": "http://example.com/property/float_value"}, "hasValue": {"value": 0.75}},
                "float_value",
                0.75,
            ),
            (
                {"property": {"@id": "http://example.com/property/none_value"}, "hasValue": {"value": None}},
                "none_value",
                None,
            ),
        ],
        ids=["test_int", "test_str", "test_float", "test_none"],
    )
    def test_extract_param_info_success(
        self, test_data: Dict[str, Any], expected_name: str, expected_value: int | float | None
    ) -> None:
        """Test that annotation parameters are correctly extracted for various valid inputs."""
        result = Annotation.model_validate(test_data)
        assert result.name == expected_name
        assert result.value == expected_value

    def test_missing_property_id(self) -> None:
        """Test that validation fails when property @id is missing."""
        test_data = {
            "property": {},  # Missing @id
            "hasValue": {"value": 10},
        }
        with pytest.raises(KeyError):
            Annotation.model_validate(test_data)

    def test_missing_property_field(self) -> None:
        """Test that validation fails when property field is missing."""
        test_data = {
            # Missing property field entirely
            "hasValue": {"value": 10}
        }
        with pytest.raises(KeyError):
            Annotation.model_validate(test_data)

    def test_missing_value(self) -> None:
        """Test that validation fails when value is missing in hasValue."""
        # Arrange
        test_data = {
            "property": {"@id": "http://example.com/property/priority"},
            "hasValue": {},  # Missing value
        }
        with pytest.raises(KeyError):
            Annotation.model_validate(test_data)

    def test_missing_has_value(self) -> None:
        """Test that validation fails when hasValue field is missing."""
        test_data = {
            "property": {"@id": "http://example.com/property/priority"}
            # Missing hasValue
        }
        with pytest.raises(KeyError):
            Annotation.model_validate(test_data)


class TestParameter:
    @pytest.mark.parametrize(
        "param_value",
        [
            (24),
            (0.75),
            ("str_value"),
            (None),
            (time(10, 30, 0)),
        ],
        ids=["test int", "test float", "test str", "test None", "test time"],
    )
    def test_extract_param_info_with_direct_value(self, param_value: Any) -> None:
        """Test parameter extraction with direct values of different types."""
        test_data = {
            "parameter": {"@id": "http://example.com/parameter/test_value"},
            "hasValue": {"value": param_value},
        }

        result = Parameter.model_validate(test_data)

        assert result.value == param_value

    @pytest.mark.parametrize(
        "param_value,expected",
        [
            ("24", 24),
            ("0.75", 0.75),
            ("str_value", "str_value"),
            (None, None),
            ("10:30:00", time(10, 30, 0)),
        ],
        ids=["test int", "test float", "test str", "test None", "test time"],
    )
    def test_extract_param_info_with_direct_string_value(self, param_value: Any, expected: Any) -> None:
        """Test parameter extraction with direct values of different types, but originally in string format"""
        test_data = {
            "parameter": {"@id": "http://example.com/parameter/test_value"},
            "hasValue": {"value": param_value},
        }
        result = Parameter.model_validate(test_data)
        assert result.value == expected

    def test_extract_param_info_with_reference(self) -> None:
        """Test parameter extraction with reference values."""
        test_data = {
            "parameter": {"@id": "http://example.com/parameter/reference_value"},
            "hasValue": {"valueReference": {"@id": "http://example.com/variable/air_temp"}},
        }

        result = Parameter.model_validate(test_data)
        assert result.name == "reference_value"
        assert result.value == "http://example.com/variable/air_temp"

    @pytest.mark.parametrize(
        "id_value,expected",
        [
            ("http://example.com/parameter/simple", "simple"),
            ("http://example.com/parameter/single-hyphen", "single_hyphen"),
            ("http://example.com/parameter/multiple-hyphen-test", "multiple_hyphen_test"),
            ("http://example.com/parameter/under_score", "under_score"),
            ("http://example.com/parameter/multiple_under_score", "multiple_under_score"),
            ("http://example.com/parameter/mix-hyphen_underscore", "mix_hyphen_underscore"),
        ],
        ids=[
            "simple",
            "with hyphen",
            "with multiple hyphen",
            "with underscore",
            "with multiple underscore",
            "hyphen underscore",
        ],
    )
    def test_parameter_name_parsing(self, id_value: str, expected: str) -> None:
        """Test parameter names are parsed appropriately.
        Note that hyphens should get turned to underscores, so duplicating the regex tests from test_common.py
        but changing result to reflect this.
        """
        test_data = {"parameter": {"@id": id_value}, "hasValue": {"value": 10}}
        result = Parameter.model_validate(test_data)
        assert result.name == expected

    def test_missing_parameter_id(self) -> None:
        """Test that validation fails when parameter @id is missing."""
        test_data = {
            "parameter": {},  # Missing @id
            "hasValue": {"value": 10},
        }
        with pytest.raises(KeyError):
            Parameter.model_validate(test_data)

    def test_missing_parameter_field(self) -> None:
        """Test that validation fails when parameter field is missing."""
        test_data = {
            # Missing parameter field entirely
            "hasValue": {"value": 10}
        }
        with pytest.raises(KeyError):
            Parameter.model_validate(test_data)

    def test_missing_has_value(self) -> None:
        """Test that validation fails when hasValue field is missing."""
        test_data = {
            "parameter": {"@id": "http://example.com/parameter/parameter_id"},
            # Missing hasValue
        }
        with pytest.raises(KeyError):
            Parameter.model_validate(test_data)


class TestConfigItem:
    """Test the ConfigItem model."""

    def test_extract_method_name(self) -> None:
        """Test extraction of method name from the @id field."""
        # Arrange
        test_data = {
            "method": {"@id": "http://example.com/method/linear-interpolation"},
        }
        result = ConfigItem.model_validate(test_data)
        assert result.name == "linear-interpolation"

    @pytest.mark.parametrize(
        "interval_name_in,interval_name_out,date_str,expected_datetime",
        [
            (a, b, c, d)
            for (a, b), (c, d) in list(
                product(
                    [("interval", "interval"), ("observationInterval", "observation_interval")],
                    [
                        ("2023-01-01T00:00:00", datetime(2023, 1, 1)),
                        ("2023-06-15T12:30:45", datetime(2023, 6, 15, 12, 30, 45)),
                        ("2023-12-31T23:59:59", datetime(2023, 12, 31, 23, 59, 59)),
                    ],
                )
            )
        ],
    )
    def test_extract_interval_only_start(
        self, interval_name_in: str, interval_name_out: str, date_str: str, expected_datetime: datetime
    ) -> None:
        """Test extraction of interval and observation interval that only includes a start date."""
        test_data = {
            "method": {"@id": "http://example.com/method/test"},
            interval_name_in: {"startDate": date_str},
        }
        result = ConfigItem.model_validate(test_data)
        assert getattr(result, interval_name_out) == (expected_datetime, None)

    @pytest.mark.parametrize(
        "interval_name_in,interval_name_out,date_str,expected_datetime",
        [
            (a, b, c, d)
            for (a, b), (c, d) in list(
                product(
                    [("interval", "interval"), ("observationInterval", "observation_interval")],
                    [
                        ("2023-01-01T00:00:01", datetime(2023, 1, 1, 0, 0, 1)),
                        ("2023-06-15T12:30:45", datetime(2023, 6, 15, 12, 30, 45)),
                        ("2023-12-31T23:59:59", datetime(2023, 12, 31, 23, 59, 59)),
                    ],
                )
            )
        ],
    )
    def test_extract_interval_only_end(
        self, interval_name_in: str, interval_name_out: str, date_str: str, expected_datetime: datetime
    ) -> None:
        """Test extraction of interval and observation interval that only includes an end date."""
        test_data = {
            "method": {"@id": "http://example.com/method/test"},
            interval_name_in: {"endDate": date_str},
        }
        result = ConfigItem.model_validate(test_data)
        assert getattr(result, interval_name_out) == (datetime(1800, 1, 1), expected_datetime)

    @pytest.mark.parametrize(
        "interval_name_in,interval_name_out,start_date,end_date,expected",
        [
            (a, b, c, d, e)
            for (a, b), (c, d, e) in list(
                product(
                    [("interval", "interval"), ("observationInterval", "observation_interval")],
                    [
                        ("2022-01-01", "2023-01-01", (datetime(2022, 1, 1), datetime(2023, 1, 1))),
                        (
                            "2022-01-01T00:00:01",
                            "2023-06-15T12:30:45",
                            (datetime(2022, 1, 1, 0, 0, 1), datetime(2023, 6, 15, 12, 30, 45)),
                        ),
                        (
                            "2023-12-31T23:59:59",
                            "2025-12-15",
                            (datetime(2023, 12, 31, 23, 59, 59), datetime(2025, 12, 15)),
                        ),
                    ],
                )
            )
        ],
    )
    def test_extract_interval(
        self,
        interval_name_in: str,
        interval_name_out: str,
        start_date: datetime,
        end_date: datetime,
        expected: tuple[datetime, datetime],
    ) -> None:
        """Test extraction of interval and observation interval with start and end dates."""
        test_data = {
            "method": {"@id": "http://example.com/method/test"},
            interval_name_in: {"startDate": start_date, "endDate": end_date},
        }
        result = ConfigItem.model_validate(test_data)
        assert getattr(result, interval_name_out) == expected

    @pytest.mark.parametrize(
        "interval_name_in,start_date,end_date",
        [
            (a, b, c)
            for a, (b, c) in list(
                product(
                    ["interval", "observationInterval"],
                    [
                        ("2023-01-01", "2023-01-01"),
                        ("2023-01-01", "2022-12-31"),
                        ("2023-01-01T12:00:00", "2023-01-01T11:59:59"),
                    ],
                )
            )
        ],
    )
    def test_invalid_end_date(self, interval_name_in: str, start_date: str, end_date: str) -> None:
        """Test validation fails when end_date is not after start_date."""
        test_data = {
            "method": {"@id": "http://example.com/method/test"},
            interval_name_in: {"startDate": start_date, "endDate": end_date},
        }
        with pytest.raises(ValueError):
            ConfigItem.model_validate(test_data)

    def test_extract_single_parameter(self) -> None:
        """Test extraction of a single parameter."""
        test_data = {
            "method": {"@id": "http://example.com/method/test"},
            "argument": [{"parameter": {"@id": "http://example.com/parameter/max-gap"}, "hasValue": {"value": 6}}],
        }
        result = ConfigItem.model_validate(test_data)
        assert len(result.parameters) == 1
        assert result.parameters["max_gap"] == 6

    def test_extract_multiple_parameters(self) -> None:
        """Test extraction of multiple parameters."""
        test_data = {
            "method": {"@id": "http://example.com/method/test"},
            "argument": [
                {"parameter": {"@id": "http://example.com/parameter/max-gap"}, "hasValue": {"value": 6}},
                {"parameter": {"@id": "http://example.com/parameter/window-size"}, "hasValue": {"value": 24}},
                {"parameter": {"@id": "http://example.com/parameter/method-type"}, "hasValue": {"value": "linear"}},
            ],
        }
        result = ConfigItem.model_validate(test_data)
        assert len(result.parameters) == 3
        assert result.parameters["max_gap"] == 6
        assert result.parameters["window_size"] == 24
        assert result.parameters["method_type"] == "linear"

    def test_extract_multiple_parameters_same_name(self) -> None:
        """Test multiple parameters with the same name should result in a list of values, not a single value."""
        test_data = {
            "method": {"@id": "http://example.com/method/test"},
            "argument": [
                {"parameter": {"@id": "http://example.com/parameter/value"}, "hasValue": {"value": 6}},
                {"parameter": {"@id": "http://example.com/parameter/value"}, "hasValue": {"value": 24}},
                {"parameter": {"@id": "http://example.com/parameter/value"}, "hasValue": {"value": "linear"}},
            ],
        }
        result = ConfigItem.model_validate(test_data)
        assert len(result.parameters) == 1
        assert result.parameters["value"] == [6, 24, "linear"]

    def test_missing_method_id(self) -> None:
        """Test that validation fails when method @id is missing."""
        test_data = {
            "method": {},  # Missing @id
        }
        with pytest.raises(KeyError):
            ConfigItem.model_validate(test_data)

    def test_missing_observation_interval(self) -> None:
        """Test that validation passes when observationInterval is missing.
        It's okay for this to be missing, as we then assume it applies for the whole time series."""
        test_data = {
            "method": {"@id": "http://example.com/method/test"},
            # Missing observationInterval
        }
        ConfigItem.model_validate(test_data)

    def test_missing_start_date(self) -> None:
        """Test that validation passes when startDate is missing.
        It's okay for this to be missing, as we then assume it applies for the whole time series."""
        test_data = {
            "method": {"@id": "http://example.com/method/test"},
            "observationInterval": {},  # Missing startDate
        }
        ConfigItem.model_validate(test_data)


class TestDataProcessingConfiguration:
    """Test the DataProcessingConfiguration model."""

    @property
    def test_data(self) -> Dict[str, Any]:
        test_data = {
            "appliesToTimeSeries": [
                {
                    "@id": "http://example.com/id/dataset/example_name",
                    "originatingSite": {"@id": "http://example.com/site/site-abcd1"},
                }
            ],
            "hasAnnotation": [
                {
                    "property": {"@id": "http://example.com/property/data-processing-configuration-priority"},
                    "hasValue": {"value": 1},
                }
            ],
            "hasCurrentConfiguration": [
                {
                    "method": {"@id": "http://example.com/method/linear-interpolation"},
                    "observationInterval": {"startDate": "2023-01-01T00:00:00"},
                    "argument": [
                        {"parameter": {"@id": "http://example.com/parameter/max-gap"}, "hasValue": {"value": 6}}
                    ],
                }
            ],
        }
        return test_data

    def test_extract_site_id(self) -> None:
        """Test extraction of site ID."""
        result = DataProcessingConfiguration.model_validate(self.test_data)
        assert result.site_id == "http://example.com/site/site-abcd1"

    def test_extract_time_series_id(self) -> None:
        """Test extraction of time series name."""
        result = DataProcessingConfiguration.model_validate(self.test_data)
        assert result.ts_id == "http://example.com/id/dataset/example_name"

    @patch("metadata_manager.models.schemas.data_processing_configurations.ConfigItem.model_validate")
    def test_extract_method_config(self, mock_method_validate: MagicMock) -> None:
        """Test extraction and validation of method configuration."""
        mock_method = MagicMock(spec=ConfigItem)
        mock_method.name = "linear-interpolation"
        mock_method_validate.return_value = mock_method

        result = DataProcessingConfiguration.model_validate(self.test_data)
        assert result.configs == [mock_method]

    def test_extract_annotations(self) -> None:
        """Test extraction and validation of method configuration."""
        result = DataProcessingConfiguration.model_validate(self.test_data)
        assert result.annotations == {"data-processing-configuration-priority": 1}

    def test_missing_applies_to_time_series(self) -> None:
        """Test that validation fails when appliesToTimeSeries is missing."""
        test_data = self.test_data.copy()
        test_data.pop("appliesToTimeSeries")
        with pytest.raises(KeyError):
            DataProcessingConfiguration.model_validate(test_data)

    def test_empty_applies_to_time_series(self) -> None:
        """Test that validation fails when appliesToTimeSeries is empty."""
        test_data = self.test_data.copy()
        test_data["appliesToTimeSeries"] = []
        with pytest.raises(IndexError):
            DataProcessingConfiguration.model_validate(test_data)

    def test_missing_has_current_configuration(self) -> None:
        """Test that validation fails when hasCurrentConfiguration is missing."""
        test_data = self.test_data.copy()
        test_data.pop("hasCurrentConfiguration")
        with pytest.raises(KeyError):
            DataProcessingConfiguration.model_validate(test_data)

    def test_empty_has_current_configuration(self) -> None:
        """Test that validation fails when hasCurrentConfiguration is empty."""
        test_data = self.test_data.copy()
        test_data["hasCurrentConfiguration"] = []
        with pytest.raises(ValueError):
            DataProcessingConfiguration.model_validate(test_data)


class TestDataProcessingConfigurations:
    @patch("metadata_manager.models.schemas.data_processing_configurations.DataProcessingConfiguration.model_validate")
    def test_model_validate_with_items_dict(self, mock_validate: MagicMock) -> None:
        """Test validation with a dictionary containing 'items'."""
        mock_config = MagicMock(spec=DataProcessingConfiguration)
        mock_validate.return_value = mock_config
        test_data = {"items": ["config1", "config2", "config3"]}

        result = DataProcessingConfigurations.model_validate(test_data)
        assert len(result) == 3

    @patch("metadata_manager.models.schemas.data_processing_configurations.DataProcessingConfiguration.model_validate")
    def test_model_validate_with_list(self, mock_validate: MagicMock) -> None:
        """Test validation with a list of items."""
        mock_config = MagicMock(spec=DataProcessingConfiguration)
        mock_validate.return_value = mock_config

        test_data = ["config1", "config2", "config3"]

        result = DataProcessingConfigurations.model_validate(test_data)
        assert len(result) == 3

    def test_model_validate_with_empty_dict_input(self) -> None:
        """Test validation with empty dict inputs."""
        result = DataProcessingConfigurations.model_validate({"items": []})
        assert len(result) == 0

    def test_model_validate_with_empty_list_input(self) -> None:
        """Test validation with empty list inputs."""
        result = DataProcessingConfigurations.model_validate([])
        assert len(result) == 0

    def test_model_validate_with_none(self) -> None:
        """Test validation with None input."""
        result = DataProcessingConfigurations.model_validate(None)
        assert len(result) == 0

    def test_model_validate_with_dict_no_items(self) -> None:
        """Test validation fails if dict input doesn't have an items key"""
        with pytest.raises(KeyError):
            DataProcessingConfigurations.model_validate({"not_items": []})
