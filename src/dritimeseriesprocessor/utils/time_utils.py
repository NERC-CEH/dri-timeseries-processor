from datetime import date, datetime, time


def to_datetime(d: date | None) -> datetime | None:
    """Convert a date to midnight datetime, leaving None unchanged."""
    if d is None:
        return None
    return datetime.combine(d, time.min)
