from datetime import datetime, timedelta

import polars as pl
from time_stream import Period, TimeSeries


def df_to_ts(df: pl.DataFrame) -> "TimeSeries":
    """Convert a Polars DataFrame to a TimeSeries object."""

    # Add time column according to the length of the DataFrame
    time_name = "time"
    date_list = [datetime(2023, 1, 1) + timedelta(days=i) for i in range(len(df))]
    df = df.with_columns(pl.Series(name="time", values=date_list))

    # Reorder columns to put "time" first
    df = df.select(["time"] + [col for col in df.columns if col != "time"])

    # Set resolution and periodicity
    resolution = Period.of_iso_duration("P1D")

    return TimeSeries(
        df=df,
        time_name=time_name,
        resolution=resolution,
        periodicity=resolution,
        metadata={},
    )
