import polars as pl

from time_series import TimeSeries


def linear_interpolation(ts: TimeSeries, column: str, flag_column: str, max_gap_size: int = None) -> pl.DataFrame:
    """
    Perform linear interpolation on a Polars Series, filling gaps that are smaller than a specified size.

    Args:
        ts: The input TimeSeries containing the data to be infilled.
        column: The name of the column to be infilled.
        flag_column: The name of the flag column to be updated with the method ID.
        max_gap_size: The maximum size of consecutive null gaps that should be filled. Any gap larger than this will not
            be interpolated and will remain as null.

    Returns:
        The TimeSeries with the infilled column and updated flag column.
    """
    # Create a new dataframe to store the original and filled values
    df = ts.df[[column]].clone()

    df = df.with_columns(pl.when(pl.col(column).is_nan()).then(None).otherwise(pl.col(column)).alias(column))

    # Detect where the values are null
    null_mask = df[column].is_null()

    if max_gap_size is None:
        df = df.with_columns(df[column].interpolate().alias("value_filled"))
    else:
        # Calculate the gaps (consecutive nulls)
        df = df.with_columns(
            # Generate a unique group number for each non-null value
            pl.when(pl.col(column).is_not_null()).then(pl.arange(0, df.height)).forward_fill().alias("group_id")
        )

        # Calculate the size of each null group
        df = df.with_columns(pl.col("group_id").filter(null_mask).count().over("group_id").alias("gap_size"))

        # Conditionally fill gaps that are smaller than the threshold
        df = df.with_columns(
            pl.when(pl.col("gap_size") <= max_gap_size)
            .then(pl.col(column).interpolate())
            .otherwise(None)
            .alias("value_filled")
        )

    # Set all original non-null values to null in the new filled column
    df = df.with_columns(
        pl.when(null_mask)  # If the original value was null
        .then(pl.col("value_filled"))  # Keep the interpolated value
        .otherwise(None)  # Set the non-null original values to null
        .alias("value_filled")
    )

    # Merge infill data into the TimeSeries object
    ts.df = ts.df.with_columns(pl.col(column).fill_null(df["value_filled"]).fill_nan(df["value_filled"]))

    # Update the flag column with the method ID
    expr = df["value_filled"].is_not_null()
    ts.add_flag(flag_column, "INTERP_LINEAR", expr)

    return ts


INFILL_METHODS = {
    "INTERP_LINEAR": linear_interpolation,
}
