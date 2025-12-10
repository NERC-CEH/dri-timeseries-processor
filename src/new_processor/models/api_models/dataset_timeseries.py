"""
Pydantic models for the Time Series Dataset, with timeseries view, metadata endpoint.

Example API call:
    https://dri-metadata-api.staging.eds.ceh.ac.uk/id/dataset/{dataset_id}.json?_view=timeseries
    https://dri-metadata-api.staging.eds.ceh.ac.uk/id/dataset/{dataset_id}/_dependencies.json
    https://dri-metadata-api.staging.eds.ceh.ac.uk/id/dataset/{dataset_id}/_all_dependencies.json

Represents metadata describing time series datasets, including their measurement details (variable, unit, resolution),
processing level, data location, etc. Used to parse and validate dataset metadata before mapping to
domain models and building dependency graphs.
"""

from pydantic import Field

from new_processor.models.api_models.shared import BaseAPIResponse, HasCurrentConfigurationItem, IDModel


class Variable(IDModel):
    """Variable with label."""

    label: list[str] | None = None
    pref_label: list[str] | None = Field(None, alias="prefLabel")


class HasUnit(IDModel):
    """Unit specification with label."""

    label: list[str] | None = None
    pref_label: list[str] | None = Field(None, alias="prefLabel")


class Aggregation(IDModel):
    """Aggregation specification."""

    value_statistic: IDModel = Field(..., alias="valueStatistic")
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
    has_current_configuration: list[HasCurrentConfigurationItem] = Field(..., alias="hasCurrentConfiguration")


class Methodology(IDModel):
    """Methodology specification."""

    uses: list[IDModel]
    configuration: Configuration


class TypeItem(IDModel):
    """Type item with processing level and measure."""

    processing_level: IDModel = Field(..., alias="processingLevel")
    measure: Measure
    methodology: Methodology | None = None


class TimeSeriesDatasetItem(IDModel):
    """Time series dataset item."""

    field_type: list[IDModel] = Field(..., alias="@type")
    type: list[TypeItem] = Field(..., min_length=1, max_length=1)
    source_bucket: str | None = Field(None, alias="sourceBucket")
    source_dataset: str | None = Field(None, alias="sourceDataset")
    source_column_name: str | None = Field(None, alias="sourceColumnName")
    originating_facility: list[IDModel] | None = Field(None, alias="originatingFacility")
    originating_site: list[IDModel] | None = Field(None, alias="originatingSite")
    depends_on: list[IDModel] = Field(default_factory=list, alias="dependsOn")
    direct_depends_on: list[IDModel] = Field(default_factory=list, alias="directDependsOn")


class TimeSeriesDatasetResponse(BaseAPIResponse):
    """Time series dataset API response."""

    items: list[TimeSeriesDatasetItem]
