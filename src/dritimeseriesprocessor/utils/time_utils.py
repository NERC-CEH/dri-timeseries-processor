from datetime import date, datetime, time


def to_datetime(d: date) -> datetime:
    """Convert a date to midnight datetime"""
    return datetime.combine(d, time.min)
