from datetime import datetime, timedelta

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
    df = pl.DataFrame({column_name: values})
    return dataframe_to_timeframe(df, metadata={"column_name": column_name})


def dataframe_to_timeframe(
    df: pl.DataFrame, time_name: str = "time", resolution: str | None = None, metadata: dict | None = None
) -> ts.TimeFrame:
    """Convert a Polars DataFrame to a ts.TimeFrame object.

    If the DataFrame containers a time column, the resolution must be specified

    If the DataFrame doesn't contain a time column, it will be added as a column of sequential hourly timestamps.

    Args:
        df: Polars DataFrame to convert to ts.TimeFrame object
        time_name: Name of the time column
        resolution: Resolution if the df contains a time column
        metadata: Optional metadata to add to the TimeFrame

    Returns:
        TimeFrame object
    """
    if time_name not in df.columns:
        date_list = [datetime(2025, 1, 1) + timedelta(hours=h) for h in range(len(df))]
        df = df.with_columns(pl.Series(name=time_name, values=date_list))
        # Reorder columns to put "time" first
        df = df.select([time_name] + [col for col in df.columns if col != time_name])
        resolution = "PT1H"
    tf = ts.TimeFrame(df=df, time_name=time_name, resolution=resolution)
    if metadata:
        tf = tf.with_metadata(metadata)
    return tf
