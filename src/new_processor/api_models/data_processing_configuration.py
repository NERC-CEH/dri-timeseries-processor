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

from pydantic import Field

from new_processor.api_models.annotation import HasAnnotationItem
from new_processor.api_models.shared import (
    BaseAPIResponse,
    HasCurrentConfigurationItem,
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
    has_current_configuration: list[HasCurrentConfigurationItem] = Field(..., alias="hasCurrentConfiguration")
    type: IDModel


class DataProcessingConfiguration(BaseAPIResponse):
    """Data processing configuration API response."""

    items: list[DataProcessingConfigurationItem]
