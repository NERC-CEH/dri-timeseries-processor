"""
Domain model representing site metadata for an observation site in the FDRI system.
"""

from dataclasses import dataclass
from datetime import datetime


@dataclass
class SiteMetadata:
    site_id: str
    network: str
    alt_id: str | None = None
    full_name: str | None = None
    easting: float | None = None
    northing: float | None = None
    lat: float | None = None
    lon: float | None = None
    altitude: float | None = None
    canopy_height: float | None = None
    displacement_height: float | None = None
    roughness_length: float | None = None
    start_date: datetime | None = None
    end_date: datetime | None = None

    def __hash__(self) -> int:
        """Allow this container to be used as a dict or set key."""
        return hash(self.site_id)
