from datetime import date, datetime, time, timedelta


def to_datetime(d: date) -> datetime:
    """Convert a date to midnight datetime"""
    return datetime.combine(d, time.min)


def extend_date_range(start_date: datetime, end_date: datetime, margin_days: int = 1) -> tuple[datetime, datetime]:
    """Widen a processing window so aggregation buckets on its edges get all of their source data.

    A bucket labelled T covers (T - period, T] or [T, T + period), depending on the time anchors of the source data
    and of the aggregated output. So a bucket at either edge of the window can need source data from outside it,
    and without that data it is built from a partial set of values.

    Args:
        start_date: Start of the requested window.
        end_date: End of the requested window.
        margin_days: Days to read either side of the window. The default of one day covers any aggregation period
            up to and including daily, which is as coarse as anything currently aggregates to. Aggregating to
            monthly would need a wider margin.

    Returns:
        The widened start and end dates to read data for.
    """
    margin = timedelta(days=margin_days)
    return start_date - margin, end_date + margin


def split_into_calendar_years(start: date | datetime, end: date | datetime) -> list[tuple[datetime, datetime]]:
    """Split a date range into calendar-year chunks, oldest first.

    Args:
        start: First day of the range (inclusive)
        end: Last day of the range (inclusive)

    Returns:
        A list of (start, end) datetimes, one per calendar year touched by the range. Empty if `end` is before `start`.
    """
    start_day = start.date() if isinstance(start, datetime) else start
    end_day = end.date() if isinstance(end, datetime) else end
    if end_day < start_day:
        return []

    chunks = []
    for year in range(start_day.year, end_day.year + 1):
        chunk_start = max(start_day, date(year, 1, 1))
        chunk_end = min(end_day, date(year, 12, 31))
        chunks.append((to_datetime(chunk_start), to_datetime(chunk_end)))
    return chunks
