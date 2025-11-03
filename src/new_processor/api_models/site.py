"""
Pydantic models for the Site metadata endpoint.

Example API call:
    https://dri-metadata-api.staging.eds.ceh.ac.uk/id/site/{site-id}.json

Represents site-level metadata returned by the FDRI metadata API, including location (geometry, coordinates, altitude),
operating periods, and related annotations. Used to validate and parse site information before mapping to
domain models.
"""

from pydantic import Field

from new_processor.api_models.annotation import HasAnnotationItem
from new_processor.api_models.shared import BaseAPIResponse, IDModel


class HasGeometryItem(IDModel):
    """Geometry specification with WKT representation."""

    field_type: list[IDModel] = Field(..., alias="@type")
    as_wkt: str = Field(..., alias="asWKT")


class OperatingPeriod(IDModel):
    """Operating period with start and end dates."""

    start_date: str = Field(..., alias="startDate")
    end_date: str = Field(..., alias="endDate")


class SiteItem(IDModel):
    """Site item with location and metadata."""

    field_type: list[IDModel] = Field(..., alias="@type")

    # Location fields
    easting: str | None = None
    northing: str | None = None
    lat: str | None = None
    long: str | None = None
    altitude: float | None = None
    has_representative_point: IDModel | None = Field(None, alias="hasRepresentativePoint")
    has_geometry: list[HasGeometryItem] | None = Field(list, alias="hasGeometry")

    # Other metadata
    has_annotation: list[HasAnnotationItem] | None = Field(list, alias="hasAnnotation")
    operating_period: OperatingPeriod | None = Field(None, alias="operatingPeriod")
    has_part: list[IDModel] | None = Field(list, alias="hasPart")
    identifier: list[str]
    comment: list[str] | None = []
    label: list[str]
    observes: list[IDModel] | None = []


class Site(BaseAPIResponse):
    """Site API response."""

    items: list[SiteItem] = Field(..., max_length=1)
