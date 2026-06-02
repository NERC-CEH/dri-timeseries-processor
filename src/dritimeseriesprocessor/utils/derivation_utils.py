import polars as pl


def rolling_mean(expr: pl.Expr, n_smooth: int, na_lim: int = 0) -> pl.Expr:
    """
    Calculate a rolling mean by averaging values within a window centred
    around each data point, n_smooth values either side. Note, this means
    values at beginning and end of data without enough values on one side of
    the data point will be NA.

    Args:
        expr - polars expression
            The data to smooth

        n_smooth - int
            The number of values on each side of a data point to include in
            the averaging

        na_lim - int (optional)
            How many NA values are allowed in averaging window before NA is
            returned. Default is 0
    """
    window_size = 2 * n_smooth

    # Count nulls in the window
    null_count = expr.is_null().rolling_sum(window_size, center=True)

    return pl.when(null_count <= na_lim).then(expr.rolling_mean(window_size, center=True)).otherwise(pl.lit(None))
