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


def create_hourly_test_data(start_date: datetime, end_date: datetime) -> None:
    """Create sample data that we have more control over for doing specific tests"""

    current_date = start_date

    data = {}

    while current_date <= end_date:
        for site in ['site1', 'site2']:
            # Create hourly data for the current date
            data = data | {
                'time': [current_date + timedelta(hours=i) for i in range(24)] * 2,
                'SITE_ID': [site] * 48,
                'col1': list(range(48)),
                'col2': list(range(48, 96))
            }

        current_date += timedelta(days=1)
    
    return pl.DataFrame(data)
