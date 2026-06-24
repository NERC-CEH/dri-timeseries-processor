"""
Pydantic models for the Observation Dataset metadata endpoint.

Represents fdri:ObservationDataset items - bundles (e.g. raw .dat files)
"""

from pydantic import Field

from dritimeseriesprocessor.models.api_models.shared import BaseAPIResponse, IDModel


class Variable(IDModel):
    """Variable with label."""

    pref_label: list[str] | None = Field(None, alias="prefLabel")


class HasUnit(IDModel):
    """Unit specification with label."""

    pref_label: list[str] | None = Field(None, alias="prefLabel")


class Measure(IDModel):
    """Measure specification with variable and unit."""

    variable: Variable | None = None
    has_unit: HasUnit | None = Field(None, alias="hasUnit")
    aggregation: IDModel | None = None
    periodicity: str | None = None
    resolution: str | None = None


class MethodologyStep(IDModel):
    """A single ordered step in a dataset's TimeSeriesPlan."""

    index: int
    configuration: IDModel


class Methodology(IDModel):
    """TimeSeriesPlan - the ordered processing steps that produce this dataset."""

    uses: list[IDModel] | None = None
    steps: list[MethodologyStep] | None = Field(None, alias="hasPart")


class Distribution(IDModel):
    """DCAT Distribution - represents an available form of a dataset.

    E.g., an S3 parquet folder with data in a specific format.
    The API serialises dct:accessURL as `accessUrl` (camelCase, lowercase l).
    The distribution property on a dataset is a list of these objects.
    """

    format: IDModel | None = None
    access_url: list[str] | None = Field(None, alias="accessUrl")


class ObservationDatasetItem(IDModel):
    """Observation dataset item - base class for TimeSeriesDatasetItem."""

    field_type: list[IDModel] = Field(..., alias="@type")
    processing_level: IDModel = Field(..., alias="processingLevel")
    measure: list[Measure] | None = None
    methodology: Methodology | None = None
    distribution: list[Distribution] | None = Field(None, alias="distribution")
    originating_facility: list[IDModel] | None = Field(None, alias="originatingFacility")
    originating_site: list[IDModel] | None = Field(None, alias="originatingSite")
    originating_programme: list[IDModel] | None = Field(None, alias="originatingProgramme")
    direct_depends_on: list[IDModel] | None = Field(None, alias="directDependsOn")

    @property
    def distribution_url(self) -> str | None:
        """Return the first access URL from the first distribution, or None."""
        if self.distribution and self.distribution[0].access_url:
            return self.distribution[0].access_url[0]
        return None


class ObservationDatasetResponse(BaseAPIResponse):
    """Observation dataset API response."""

    items: list[ObservationDatasetItem]
