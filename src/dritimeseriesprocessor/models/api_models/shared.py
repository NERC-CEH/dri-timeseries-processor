"""
Shared Pydantic components used across metadata API models.

Provides reusable base classes and common field definitions shared by multiple FDRI metadata endpoints,
including ID structures, metadata headers, value representations, and configuration item templates.

These models ensure consistent validation and alias mapping across all API response types.
"""

from datetime import datetime
from typing import Any, Self

from pydantic import BaseModel, Field, model_validator
from pydantic_core import PydanticCustomError


class IDModel(BaseModel):
    """Base model with ID."""

    id: str = Field(..., alias="@id")


class Meta(IDModel):
    """Metadata for API responses."""

    publisher: str
    license: str
    license_name: str = Field(..., alias="licenseName")
    comment: str
    version: str
    has_format: list[str] = Field(..., alias="hasFormat")


class ObservationInterval(IDModel):
    """Represents an observation interval with start and (optional) end dates."""

    field_type: list[IDModel] = Field(..., alias="@type")
    start_date: datetime = Field(..., alias="startDate")
    end_date: datetime | None = Field(None, alias="endDate")


class HasValue(IDModel):
    """Represents a value with type information."""

    field_type: list[IDModel] | None = Field(None, alias="@type")
    value: list[Any] | int | float | str | list[str] | None = None
    value_reference: IDModel | list[IDModel] | None = Field(None, alias="valueReference")

    @model_validator(mode="after")
    def ensure_value_or_reference(self) -> Self:
        if self.value is None and self.value_reference is None:
            raise PydanticCustomError(
                "missing_value_or_reference", "Either 'value' or 'valueReference' must be provided."
            )
        return self


class HasStructuredValue(IDModel):
    """Represents a structured value, that can be used to link to other metadata."""

    argument: list["ArgumentItem"] = Field(default_factory=list)


class ArgumentItem(IDModel):
    """Configuration argument with parameter and value."""

    field_type: list[IDModel] | None = Field(None, alias="@type")
    has_value: HasValue | None = Field(None, alias="hasValue")
    has_structured_value: HasStructuredValue | None = Field(None, alias="hasStructuredValue")
    parameter: IDModel

    @model_validator(mode="after")
    def ensure_has_value_or_has_structured_value(self) -> Self:
        if self.has_value is None and self.has_structured_value is None:
            raise PydanticCustomError(
                "missing_has_value_or_has_structured_value",
                "Either 'hasValue' or 'hasStructuredValue' must be provided.",
            )
        return self


class HasCurrentValue(IDModel):
    """Has current value item with optional method."""

    field_type: list[IDModel] | None = Field(None, alias="@type")
    method: IDModel | None = None
    argument: list[ArgumentItem] = Field(default_factory=list)
    observation_interval: ObservationInterval | None = Field(None, alias="observationInterval")


class HadValue(IDModel):
    """Had value item"""

    field_type: list[IDModel] | None = Field(None, alias="@type")
    argument: list[ArgumentItem] = Field(default_factory=list)
    observation_interval: ObservationInterval | None = Field(None, alias="observationInterval")


class BaseAPIResponse(BaseModel):
    """Base class for API responses with metadata."""

    meta: Meta
    items: list
