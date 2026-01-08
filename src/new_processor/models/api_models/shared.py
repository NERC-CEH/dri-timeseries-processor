"""
Shared Pydantic components used across metadata API models.

Provides reusable base classes and common field definitions shared by multiple FDRI metadata endpoints,
including ID structures, metadata headers, value representations, and configuration item templates.

These models ensure consistent validation and alias mapping across all API response types.
"""

from datetime import datetime
from typing import Self

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
    value: int | float | str | list[str] | None = None
    value_reference: IDModel | None = Field(None, alias="valueReference")

    @model_validator(mode="after")
    def ensure_value_or_reference(self) -> Self:
        if self.value is None and self.value_reference is None:
            raise PydanticCustomError(
                "missing_value_or_reference", "Either 'value' or 'valueReference' must be provided."
            )
        return self


class ArgumentItem(IDModel):
    """Configuration argument with parameter and value."""

    field_type: list[IDModel] | None = Field(None, alias="@type")
    has_value: HasValue = Field(..., alias="hasValue")
    parameter: IDModel


class HasCurrentConfigurationItem(IDModel):
    """Base configuration item with method."""

    field_type: list[IDModel] | None = Field(None, alias="@type")
    method: IDModel | None = None
    argument: list[ArgumentItem] = Field(default_factory=list)
    observation_interval: ObservationInterval | None = Field(None, alias="observationInterval")


class BaseAPIResponse(BaseModel):
    """Base class for API responses with metadata."""

    meta: Meta
    items: list
