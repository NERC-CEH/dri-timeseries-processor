"""
Pydantic models for the Site metadata endpoint.

Example API call:
    https://dri-metadata-api.staging.eds.ceh.ac.uk/id/site/{site-id}.json

Represents site-level metadata returned by the FDRI metadata API, including location (geometry, coordinates, altitude),
operating periods, and related annotations. Used to validate and parse site information before mapping to
domain models.
"""

from pydantic import Field

from dritimeseriesprocessor.models.api_models.annotation import HasAnnotationItem
from dritimeseriesprocessor.models.api_models.shared import BaseAPIResponse, IDModel


class HasGeometryItem(IDModel):
    """Geometry specification with WKT representation."""

    field_type: list[IDModel] = Field(..., alias="@type")
    as_wkt: str = Field(..., alias="asWKT")


class OperatingPeriod(IDModel):
    """Operating period with start and end dates."""

    start_date: str = Field(..., alias="startDate")
    end_date: str | None = Field(None, alias="endDate")


class UtilisedBy(IDModel):
    """Utilised by field - indicating the programme the site belongs to"""

    label: list[str] | None = Field(default_factory=list)


class SiteItem(IDModel):
    """Site item with location and metadata."""

    field_type: list[IDModel] | None = Field(None, alias="@type")

    # Location fields
    easting: float | None = None
    northing: float | None = None
    lat: float | None = None
    long: float | None = None
    altitude: float | None = None
    has_representative_point: IDModel | None = Field(None, alias="hasRepresentativePoint")
    has_geometry: list[HasGeometryItem] | None = Field(default_factory=list, alias="hasGeometry")

    # Other metadata
    has_annotation: list[HasAnnotationItem] | None = Field(default_factory=list, alias="hasAnnotation")
    operating_period: OperatingPeriod | None = Field(None, alias="operatingPeriod")
    has_part: list[IDModel] | None = Field(default_factory=list, alias="hasPart")
    identifier: list[str] | None = Field(default_factory=list)
    comment: list[str] | None = Field(default_factory=list)
    label: list[str] | None = Field(default_factory=list)
    observes: list[IDModel] | None = Field(default_factory=list)
    utilised_by: list[UtilisedBy] | None = Field(None, alias="utilisedBy")


class SiteResponse(BaseAPIResponse):
    """Site API response."""

    items: list[SiteItem]
