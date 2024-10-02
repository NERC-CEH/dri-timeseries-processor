import polars as pl


def linear_interpolation(data: pl.Series, max_gap_size: int = None) -> pl.DataFrame:
    """
    Perform linear interpolation on a Polars Series, filling gaps that are smaller than a specified size.

    Parameters:
    -----------
    data : pl.Series
        The input series containing the values with potential gaps (null values).
    max_gap : int, optional, default=None
        The maximum size of consecutive null gaps that should be filled. Any gap larger than this will not
        be interpolated and will remain as null.

    Returns:
    --------
    pl.DataFrame
        A DataFrame with three columns:
        - 'value': The original values from the input series.
        - 'value_filled': The interpolated values, with non-null original values replaced by null.
        - 'method_id': A column indicating where linear interpolation occurred, marked with 'INTERP_LINEAR',
          and None otherwise.
    """
    # Convert series to DataFrame
    df = pl.DataFrame({"value": data})

    # Detect where the values are null
    null_mask = data.is_null()

    if max_gap_size is None:
        df = df.with_columns(pl.col("value").interpolate().alias("value_filled"))
    else:
        # Calculate the gaps (consecutive nulls)
        df = df.with_columns(
            # Generate a unique group number for each non-null value
            pl.when(pl.col("value").is_not_null()).then(pl.arange(0, df.height)).forward_fill().alias("group_id")
        )

        # Calculate the size of each null group
        df = df.with_columns(pl.col("group_id").filter(null_mask).count().over("group_id").alias("gap_size"))

        # Conditionally fill gaps that are smaller than the threshold
        df = df.with_columns(
            pl.when(pl.col("gap_size") < max_gap_size)
            .then(pl.col("value").interpolate())
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

    df = df.with_columns(
        pl.when(pl.col("value_filled").is_not_null()).then(pl.lit("INTERP_LINEAR")).otherwise(None).alias("method_id")
    )

    return df["value", "value_filled", "method_id"]


INFILL_METHODS = {
    "INTERP_LINEAR": linear_interpolation,
}
