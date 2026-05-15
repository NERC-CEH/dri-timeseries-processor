"""
Pydantic models for the Observation Dataset metadata endpoint.

Represents fdri:ObservationDataset items — bundles (e.g. raw .dat files)
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


class Distribution(IDModel):
    """DCAT Distribution — represents an available form of a dataset.

    E.g., an S3 parquet folder with data in a specific format.
    The API serialises dct:accessURL as `accessUrl` (camelCase, lowercase l).
    The distribution property on a dataset is a list of these objects.
    """

    access_url: str | None = Field(None, alias="accessUrl")
    format: str | None = None


class ObservationDatasetItem(IDModel):
    """Observation dataset item — base class for TimeSeriesDatasetItem."""

    field_type: list[IDModel] = Field(..., alias="@type")
    processing_level: IDModel = Field(..., alias="processingLevel")
    measure: list[Measure]
    methodology: Methodology | None = None
    distributions: list[Distribution] | None = Field(None, alias="distribution")
    originating_facility: list[IDModel] | None = Field(None, alias="originatingFacility")
    originating_site: list[IDModel] | None = Field(None, alias="originatingSite")
    originating_programme: list[IDModel] | None = Field(None, alias="originatingProgramme")
    depends_on: list[IDModel] | None = Field(None, alias="dependsOn")
    direct_depends_on: list[IDModel] | None = Field(None, alias="directDependsOn")

    @property
    def distribution_url(self) -> str | None:
        """Return the first distribution's S3 access URL, or None.

        The API returns distributions as a list; we use the first one.
        For EddyPro raw bundles this is the S3 folder path for the .dat files.
        """
        if self.distributions:
            return self.distributions[0].access_url
        return None


class ObservationDatasetResponse(BaseAPIResponse):
    """Observation dataset API response."""

    items: list[ObservationDatasetItem]
