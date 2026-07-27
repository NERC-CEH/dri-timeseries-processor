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
