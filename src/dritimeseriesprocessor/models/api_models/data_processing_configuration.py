"""
Pydantic models for the Data Processing Configuration metadata endpoint.

Example API call:
    https://dri-metadata-api.staging.eds.ceh.ac.uk/id/data-processing-configuration.json?appliesToTimeSeries={dataset_id}&type=http://fdri.ceh.ac.uk/ref/common/configuration-type/qc
    https://dri-metadata-api.staging.eds.ceh.ac.uk/id/data-processing-configuration.json?appliesToTimeSeries={dataset_id}&type=http://fdri.ceh.ac.uk/ref/common/configuration-type/infill-configuration
    https://dri-metadata-api.staging.eds.ceh.ac.uk/id/data-processing-configuration.json?appliesToTimeSeries={dataset_id}&type=http://fdri.ceh.ac.uk/ref/common/configuration-type/correction-configuration

Description:
    Represents configuration metadata that defines processing steps applied to a time-series dataset,
    including quality control (QC), correction, and infill rules. Each configuration specifies the parameters,
    methods, and any dependencies (e.g., on other time series) required for processing.
"""

from typing import Self

from pydantic import Field, model_validator
from pydantic_core import PydanticCustomError

from dritimeseriesprocessor.models.api_models.annotation import HasAnnotationItem
from dritimeseriesprocessor.models.api_models.shared import (
    BaseAPIResponse,
    HadValue,
    HasCurrentValue,
    IDModel,
)


class AppliesToTimeSeries(IDModel):
    """Time series application specification."""

    originating_site: IDModel = Field(..., alias="originatingSite")


class DataProcessingConfigurationItem(IDModel):
    """Data processing configuration item."""

    field_type: list[IDModel] = Field(..., alias="@type")
    applies_to_time_series: list[AppliesToTimeSeries] = Field(..., alias="appliesToTimeSeries")
    has_annotation: list[HasAnnotationItem] = Field(default_factory=list, alias="hasAnnotation")
    has_current_value: list[HasCurrentValue] | None = Field(default_factory=list, alias="hasCurrentValue")
    had_value: list[HadValue] | None = Field(default_factory=list, alias="hadValue")
    type: IDModel

    @model_validator(mode="after")
    def ensure_has_current_value_or_had_value(self) -> Self:
        if self.has_current_value is None and self.had_value is None:
            raise PydanticCustomError(
                "missing_has_current_value_or_had_value", "Either 'hasCurrentValue' or 'hadValue' must be provided."
            )
        return self


class DataProcessingConfiguration(BaseAPIResponse):
    """Data processing configuration API response."""

    items: list[DataProcessingConfigurationItem]
