from datetime import datetime, timedelta

import polars as pl
import time_stream as ts


def df_to_ts(df: pl.DataFrame) -> ts.TimeFrame:
    """Convert a Polars DataFrame to a ts.TimeFrame object."""

    # Add time column according to the length of the DataFrame
    time_name = "time"
    date_list = [datetime(2023, 1, 1) + timedelta(days=i) for i in range(len(df))]
    df = df.with_columns(pl.Series(name="time", values=date_list))

    # Reorder columns to put "time" first
    df = df.select(["time"] + [col for col in df.columns if col != "time"])

    # Set resolution and periodicity
    resolution = ts.Period.of_iso_duration("P1D")

    return ts.TimeFrame(
        df=df,
        time_name=time_name,
        resolution=resolution,
        periodicity=resolution,
    )


def create_test_operation_ts(data: list | None = None) -> ts.TimeFrame:
    """Set up test fixtures."""
    if data is None:
        data = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0]

    df = pl.DataFrame(
        {
            "timestamp": [datetime(2025, m, 1) for m in range(1, 8)],
            "value": data,
        }
    )

    return ts.TimeFrame(df, "timestamp").with_metadata({"column_name": "value"})


def create_test_filter() -> pl.Expr:
    """Set up a date filter for tests."""
    start_date = datetime(2025, 3, 1)
    end_date = datetime(2025, 5, 1)
    time_name = "timestamp"
    return pl.col(time_name).is_between(start_date, end_date)
