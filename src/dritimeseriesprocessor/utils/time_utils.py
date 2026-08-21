from datetime import date, datetime, time, timedelta


def to_datetime(d: date) -> datetime:
    """Convert a date to midnight datetime"""
    return datetime.combine(d, time.min)


def year_chunks(start_date: datetime, end_date: datetime) -> list[tuple[datetime, datetime]]:
    """Split a date range into calendar-year sub-ranges.

    Args:
        start_date: Start of the range (inclusive).
        end_date: End of the range (inclusive).

    Returns:
        A list of (chunk_start, chunk_end) pairs covering [start_date, end_date], split at calendar-year
        boundaries. A range that falls within a single year returns a single chunk equal to the original range.
    """
    chunks = []
    current_start = start_date
    while current_start <= end_date:
        year_end = datetime(current_start.year, 12, 31)
        chunk_end = min(year_end, end_date)
        chunks.append((current_start, chunk_end))
        current_start = datetime(chunk_end.year + 1, 1, 1)
    return chunks


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
