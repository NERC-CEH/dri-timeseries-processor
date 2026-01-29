import pytest
from driutils.metadata_api.models.annotations import HasAnnotationItem
from pydantic import ValidationError
from tests.utils.fixture_helpers import load_json_string
from tests.utils.validation_helpers import assert_pydantic_validation_error_cause


class TestAnnotation:
    def test_basic_annotation(self) -> None:
        data = load_json_string("""{
            "@id": "http://fdri.ceh.ac.uk/id/annotation/example-1",
            "property": {"@id": "http://fdri.ceh.ac.uk/ref/common/cop/comment"},
            "hasValue": {
                "@id": "http://fdri.ceh.ac.uk/id/value/example-1",
                "value": 123,
                "@type": [{"@id": "http://schema.org/PropertyValue"}]
            }
        }""")
        result = HasAnnotationItem.model_validate(data)
        assert result.id == "http://fdri.ceh.ac.uk/id/annotation/example-1"
        assert result.property.id.endswith("comment")
        assert result.has_value.value == 123
        assert result.has_value_series is None

    def test_annotation_with_value_series(self) -> None:
        data = load_json_string("""{
            "@id": "http://fdri.ceh.ac.uk/id/annotation/example-2",
            "property": {"@id": "http://fdri.ceh.ac.uk/ref/common/cop/status"},
            "hasValueSeries": {
                "@id": "http://fdri.ceh.ac.uk/id/value-series/example-2",
                "hasCurrentValue": [
                    {
                        "@id": "http://fdri.ceh.ac.uk/id/current/example-2",
                        "@type": [{"@id": "http://fdri.ceh.ac.uk/vocab/metadata/CurrentValue"}],
                        "interval": {
                            "startDate": "2025-01-01T00:00:00",
                            "endDate": "2025-12-31T23:59:59"
                        },
                        "qualifier": [
                            {
                                "@id": "http://fdri.ceh.ac.uk/id/qualifier/q1",
                                "@type": [{"@id": "http://schema.org/PropertyValue"}],
                                "property": {"@id": "http://fdri.ceh.ac.uk/ref/common/cop/quality"},
                                "hasValue": {
                                    "@id": "http://fdri.ceh.ac.uk/id/value/q1",
                                    "value": "Good",
                                    "@type": [{"@id": "http://schema.org/PropertyValue"}]
                                }
                            }
                        ],
                        "valueReference": {"@id": "http://fdri.ceh.ac.uk/id/value/v1"}
                    }
                ]
            }
        }""")
        result = HasAnnotationItem.model_validate(data)
        assert result.has_value_series is not None
        current = result.has_value_series.has_current_value[0]
        assert current.interval.start_date.year == 2025
        assert current.qualifier[0].has_value.value == "Good"

    @pytest.mark.parametrize(
        "test_data,expected_value",
        [
            (
                '{"@id": "int", "property": {"@id": "int_value"}, "hasValue": {"@id": "id", "value": 10}}',
                10,
            ),
            (
                '{"@id": "str", "property": {"@id": "str_value"}, "hasValue": {"@id": "id", "value": "example"}}',
                "example",
            ),
            (
                '{"@id": "float", "property": {"@id": "float_value"}, "hasValue": {"@id": "id", "value": 0.75}}',
                0.75,
            ),
            (
                '{"@id": "bool", "property": {"@id": "bool_value"}, "hasValue": {"@id": "id", "value": true}}',
                True,
            ),
        ],
        ids=["test_int", "test_str", "test_float", "test_bool"],
    )
    def test_extract_param_info_success(self, test_data: str, expected_value: int | float | None) -> None:
        """Test that annotation parameters are correctly extracted for various valid inputs."""
        data = load_json_string(test_data)
        result = HasAnnotationItem.model_validate(data)
        assert result.has_value.value == expected_value

    def test_value_equal_none_raises_error(self) -> None:
        """Test that a value with explicit value of "null" (loads as None in python) raises validation error"""
        test_data = '{"@id": "none", "property": {"@id": "none_value"}, "hasValue": {"@id": "id", "value": null}}'
        data = load_json_string(test_data)

        with pytest.raises(ValidationError) as err:
            HasAnnotationItem.model_validate(data)

        # Verify what caused the error
        assert_pydantic_validation_error_cause(err, 1, "missing_value_or_reference", ("hasValue",))

    def test_missing_property_id(self) -> None:
        """Test that validation fails when property @id is missing."""
        test_data = {
            "@id": "missing_property_id",
            "property": {},  # Missing @id
            "hasValue": {"@id": "id", "value": 10},
        }
        with pytest.raises(ValidationError) as err:
            HasAnnotationItem.model_validate(test_data)

        # Verify what caused the error
        assert_pydantic_validation_error_cause(err, 1, "missing", ("property", "@id"))

    def test_missing_property_field(self) -> None:
        """Test that validation fails when property field is missing."""
        test_data = {
            "@id": "missing_property_field",
            # Missing property field entirely
            "hasValue": {"@id": "id", "value": 10},
        }
        with pytest.raises(ValidationError) as err:
            HasAnnotationItem.model_validate(test_data)

        # Verify what caused the error
        assert_pydantic_validation_error_cause(err, 1, "missing", ("property",))

    def test_missing_value(self) -> None:
        """Test that validation fails when value or valueReference is missing in hasValue"""
        test_data = {
            "@id": "missing_value",
            "property": {"@id": "priority"},
            "hasValue": {"@id": "id"},  # Missing value or valueReference within the hasValue dict
        }
        with pytest.raises(ValidationError) as err:
            HasAnnotationItem.model_validate(test_data)

        # Verify what caused the error
        assert_pydantic_validation_error_cause(err, 1, "missing_value_or_reference", ("hasValue",))

    def test_missing_has_value(self) -> None:
        """Test that validation fails when hasValue or hasValueSeries field is completely missing."""
        test_data = {
            "@id": "missing_hasValue",
            "property": {"@id": "priority"},
            # Missing hasValue or hasValueSeries
        }
        with pytest.raises(ValidationError) as err:
            HasAnnotationItem.model_validate(test_data)

        # Verify what caused the error
        assert_pydantic_validation_error_cause(err, 1, "missing_value_or_value_series")
