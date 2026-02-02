"""
Pydantic models for annotation structures used across metadata endpoints.

Annotations describe additional metadata properties attached to datasets, sites, or configurations in the
FDRI metadata API.
"""

from datetime import datetime
from typing import Self

from pydantic import BaseModel, Field, model_validator
from pydantic_core import PydanticCustomError

from dritimeseriesprocessor.models.api_models.shared import HasValue, IDModel


class QualifierItem(IDModel):
    """Qualifier with property and value."""

    field_type: list[IDModel] = Field(..., alias="@type")
    has_value: HasValue = Field(..., alias="hasValue")
    property: IDModel


class Interval(BaseModel):
    """Represents a time interval with start and end dates."""

    start_date: datetime | None = Field(None, alias="startDate")
    end_date: datetime | None = Field(None, alias="endDate")


class HasCurrentValueItem(IDModel):
    """Current value with interval and qualifiers."""

    field_type: list[IDModel] = Field(..., alias="@type")
    interval: Interval | None = None
    qualifier: list[QualifierItem]
    value_reference: list[IDModel] = Field(default_factory=list, alias="valueReference")


class HasValueSeries(IDModel):
    """Series of values with current values."""

    has_current_value: list[HasCurrentValueItem] = Field(..., alias="hasCurrentValue")


class HasAnnotationItem(IDModel):
    """Annotation item with property and values."""

    property: IDModel
    has_value: HasValue | None = Field(None, alias="hasValue")
    has_value_series: HasValueSeries | None = Field(None, alias="hasValueSeries")

    @model_validator(mode="after")
    def ensure_value_or_value_series(self) -> Self:
        if self.has_value is None and self.has_value_series is None:
            raise PydanticCustomError(
                "missing_value_or_value_series", "Either 'hasValue' or 'hasValueSeries' must be provided."
            )
        return self
