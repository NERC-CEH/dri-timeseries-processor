"""
Pydantic models for the Time Series Dataset, with timeseries view, metadata endpoint.

Example API call:
    https://dri-metadata-api.staging.eds.ceh.ac.uk/id/dataset/{dataset_id}.json?_view=timeseries

Represents metadata describing time series datasets, including their measurement details (variable, unit, resolution),
processing level, data location, etc. Used to parse and validate dataset metadata before mapping to
domain models and building dependency graphs.
"""

from pydantic import Field

from dritimeseriesprocessor.models.api_models.shared import BaseAPIResponse, HasCurrentValue, IDModel


class Variable(IDModel):
    """Variable with label."""

    pref_label: list[str] | None = Field(None, alias="prefLabel")


class HasUnit(IDModel):
    """Unit specification with label."""

    pref_label: list[str] | None = Field(None, alias="prefLabel")


class Aggregation(IDModel):
    """Aggregation specification."""

    periodicity: str
    resolution: str


class Measure(IDModel):
    """Measure specification with variable and unit."""

    variable: Variable
    has_unit: HasUnit = Field(..., alias="hasUnit")
    aggregation: Aggregation


class Configuration(IDModel):
    """Configuration with type and current configuration."""

    type: IDModel
    has_current_configuration: list[HasCurrentValue] | None = Field(None, alias="hasCurrentConfiguration")


class Methodology(IDModel):
    """Methodology specification."""

    configuration: Configuration


class TimeSeriesDatasetItem(IDModel):
    """Time series dataset item."""

    field_type: list[IDModel] = Field(..., alias="@type")
    processing_level: IDModel = Field(..., alias="processingLevel")
    measure: list[Measure]
    methodology: Methodology | None = None
    source_bucket: str | None = Field(None, alias="sourceBucket")
    source_dataset: str | None = Field(None, alias="sourceDataset")
    source_column_name: str | None = Field(None, alias="sourceColumnName")
    time_column_name: str | None = Field(None, alias="sourceTimeColumnName")
    originating_facility: list[IDModel] | None = Field(None, alias="originatingFacility")
    originating_site: list[IDModel] | None = Field(None, alias="originatingSite")
    originating_programme: list[IDModel] | None = Field(None, alias="originatingProgramme")


class TimeSeriesDatasetResponse(BaseAPIResponse):
    """Time series dataset API response."""

    items: list[TimeSeriesDatasetItem]
