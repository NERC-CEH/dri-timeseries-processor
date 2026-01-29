"""
Shared Pydantic components used across metadata API models.

Provides reusable base classes and common field definitions shared by multiple FDRI metadata endpoints,
including ID structures, metadata headers, value representations, and configuration item templates.

These models ensure consistent validation and alias mapping across all API response types.
"""

from driutils.metadata_api.models.shared import HasValue, IDModel, ObservationInterval
from pydantic import Field


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
