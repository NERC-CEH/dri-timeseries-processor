"""
Domain model representing site metadata for an observation site in the FDRI system.
"""

from dataclasses import dataclass
from datetime import datetime, time, timedelta


@dataclass
class SiteMetadata:
    site_id: str
    network: str | None
    alt_id: str | None = None
    full_name: str | None = None
    easting: float | None = None
    northing: float | None = None
    lat: float | None = None
    lon: float | None = None
    altitude: float | None = None
    start_date: datetime | None = None
    end_date: datetime | None = None
    annotations: dict | None = None

    def is_active(self, window_start: datetime | None = None, window_end: datetime | None = None) -> bool:
        """Return whether site is active during given datetime window.

        A site is considered active if:
        - It started before the window ends, AND
        - It had not ended before the window starts (no end date = still active)

        Args:
            window_start: Start of the window
            window_end: End of the window

        Returns:
            Boolean of whether site is active during the given window
        """
        if window_end is not None and self.start_date is not None:
            day_after_last_day = datetime.combine(window_end.date() + timedelta(days=1), time.min)
            if self.start_date >= day_after_last_day:
                return False

        if window_start is not None and self.end_date is not None:
            first_day_start = datetime.combine(window_start.date(), time.min)
            if self.end_date <= first_day_start:
                return False

        return True

    def __hash__(self) -> int:
        """Allow this container to be used as a dict or set key."""
        return hash(self.site_id)
