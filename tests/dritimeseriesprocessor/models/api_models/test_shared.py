import pytest
from pydantic import ValidationError

from dritimeseriesprocessor.models.api_models.shared import (
    ArgumentItem,
    BaseAPIResponse,
    HasCurrentValue,
    HasValue,
    IDModel,
    Meta,
)


class TestIDModel:
    def test_simple_parsing(self) -> None:
        """Test that model maps id alias correctly."""
        data = {"@id": "http://example.com/id/test"}
        model = IDModel.model_validate(data)
        assert model.id == "http://example.com/id/test"

    def test_missing_id_raises(self) -> None:
        """Test that model raises error if '@id' missing."""
        with pytest.raises(ValidationError) as err:
            IDModel.model_validate({})
        assert err.value.errors()[0]["loc"] == ("@id",)


class TestMeta:
    def test_field_aliases_and_values(self) -> None:
        """Test that Meta fields and aliases validate correctly."""
        data = {
            "@id": "http://example.com/meta",
            "publisher": "UKCEH",
            "license": "OGL3",
            "licenseName": "OGL3",
            "comment": "example",
            "version": "1.0",
            "hasFormat": ["json"],
        }
        meta = Meta.model_validate(data)
        assert meta.id == "http://example.com/meta"
        assert meta.publisher == "UKCEH"
        assert meta.license == "OGL3"
        assert meta.license_name == "OGL3"
        assert meta.comment == "example"
        assert meta.version == "1.0"
        assert meta.has_format == ["json"]


class TestHasValue:
    def test_with_value(self) -> None:
        """Test that a direct numeric value is accepted."""
        data = {"@id": "1", "@type": [], "value": 42}
        model = HasValue.model_validate(data)
        assert model.value == 42
        assert model.value_reference is None

    def test_with_value_reference(self) -> None:
        """Test that valueReference is accepted instead of value."""
        data = {"@id": "1", "@type": [], "valueReference": {"@id": "ref-1"}}
        model = HasValue.model_validate(data)
        assert model.value_reference.id == "ref-1"  # type: ignore[union-attr]
        assert model.value is None

    def test_missing_both_normalises_to_empty(self) -> None:
        """Test that missing both value and valueReference normalises to an empty string value."""
        data = {"@id": "1"}
        model = HasValue.model_validate(data)
        assert model.value == [""]
        assert model.value_reference is None


class TestArgumentItem:
    def test_single_has_structured_value_is_normalised_to_list(self) -> None:
        """Tests that a single hasStructuredValue object is put into a one-item list."""
        data = {
            "@id": "arg-1",
            "parameter": {"@id": "param-1"},
            "hasStructuredValue": {"@id": "sv-1"},
        }
        result = ArgumentItem.model_validate(data)
        assert isinstance(result.has_structured_value, list)
        assert len(result.has_structured_value) == 1
        assert result.has_structured_value[0].id == "sv-1"

    def test_list_has_structured_value_is_unchanged(self) -> None:
        """Tests that a hasStructuredValue already given as a list is left as-is."""
        data = {
            "@id": "arg-1",
            "parameter": {"@id": "param-1"},
            "hasStructuredValue": [{"@id": "sv-1"}, {"@id": "sv-2"}],
        }
        result = ArgumentItem.model_validate(data)
        assert isinstance(result.has_structured_value, list)
        assert len(result.has_structured_value) == 2


class TestHasCurrentConfigurationItem:
    def test_optional_method(self) -> None:
        """Test that the optional method fields can be omitted."""
        data = {"@id": "config-1"}
        model = HasCurrentValue.model_validate(data)
        assert model.method is None
        assert model.field_type is None


class TestBaseAPIResponse:
    def test_valid_response(self) -> None:
        """Test that a simple valid API response is successful."""
        data = {
            "meta": {
                "@id": "http://example.com/meta",
                "publisher": "UKCEH",
                "license": "OGL3",
                "licenseName": "OGL3",
                "comment": "example",
                "version": "1.0",
                "hasFormat": ["json"],
            },
            "items": [],
        }
        response = BaseAPIResponse.model_validate(data)

        assert response.meta.id == "http://example.com/meta"
        assert response.meta.publisher == "UKCEH"
        assert response.meta.license == "OGL3"
        assert response.meta.license_name == "OGL3"
        assert response.meta.comment == "example"
        assert response.meta.version == "1.0"
        assert response.meta.has_format == ["json"]
        assert response.items == []

    def test_missing_meta_raises(self) -> None:
        """Test that a missing meta field raises a validation error."""
        with pytest.raises(ValidationError):
            BaseAPIResponse.model_validate({"items": []})
