import polars as pl


def rolling_mean(expr: pl.Expr, n_smooth: int, na_lim: int = 0) -> pl.Expr:
    """
    Calculate a rolling mean by averaging values within a window centred
    around each data point, using n_smooth values either side. Note, this means
    values at beginning and end of data without enough values on one side of
    the data point will be null. Null values do not have a rolling mean applied.

    Why we must roll our own rolling_mean method here:
    The polars inbuilt rolling_mean method assigns a rolling mean to null values,
    and assigns a rolling mean to edges if there are n_smooth - na_lim values available in the window.
    TimeStream's rolling_aggregation method only applies to TimeFrame objects, not polars expressions,
    which are used for derivation methods.

    Args:

        expr - polars expression
            The data to smooth.

        n_smooth - int
            The number of values on each side of a data point to include in
            the averaging.

        na_lim - int (optional)
            How many null values are allowed in averaging window before null is
            returned. Default is 0

    Returns: polars expression of rolling mean
    """
    # odd window_size ensures window is symmetric, with n_smooth datapoints on each side.
    window_size = 2 * n_smooth + 1

    # Count nulls in the window.
    null_count = expr.is_null().rolling_sum(window_size, center=True, min_samples=window_size)

    return (
        pl.when((null_count <= na_lim) & expr.is_not_null())
        .then(expr.rolling_mean(window_size, center=True, min_samples=window_size - na_lim))
        .otherwise(pl.lit(None, dtype=pl.Float64))
    )
