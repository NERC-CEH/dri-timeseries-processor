from datetime import datetime

import polars as pl
import time_stream as ts


def create_timeframe(values: list[float] | None = None, column_name: str = "value") -> ts.TimeFrame:
    """Create a test TimeFrame with sequential hourly timestamps.

    Args:
        values: Optional list of values
        column_name: Name of the data column

    Returns:
        TimeFrame with test data
    """
    if values is None:
        values = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0]

    df = pl.DataFrame(
        {
            "time": [datetime(2025, 1, 1, h) for h in range(len(values))],
            column_name: values,
        }
    )

    return ts.TimeFrame(df=df, resolution="PT1H", time_name="time").with_metadata({"column_name": column_name})
