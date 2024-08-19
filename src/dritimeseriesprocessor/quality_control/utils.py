import polars as pl

from dritimeseriesprocessor.__metadata__.config_quality_control import get_qc_config


def column_threshold_check(
    df: pl.DataFrame,
    check_column: str,
    qc_column: str,
    threshold: float,
    operator: str,
    flag_value: int,
    flag_na: bool = False,
) -> pl.DataFrame:
    operator_map = {
        ">": pl.col(check_column).gt(threshold),
        ">=": pl.col(check_column).ge(threshold),
        "<": pl.col(check_column).lt(threshold),
        "<=": pl.col(check_column).le(threshold),
        "==": pl.col(check_column).eq(threshold),
        "!=": pl.col(check_column).ne(threshold),
    }

    if check_column not in df:
        raise UserWarning(f"Can not run column threshold check. No {check_column} data provided")

    if qc_column not in df:
        raise UserWarning(f"Can not run column threshold check. No {qc_column} data provided")

    if operator not in operator_map:
        raise ValueError(f"{operator} is an invalid operator, use: {', '.join(operator_map.keys())}")

    # Get the operator expression
    operator_expr = operator_map[operator]
    if flag_na:
        operator_expr = operator_expr | pl.col(check_column).is_null()

    # Apply the flags based on comparing requested column to the threshold
    df, flag_column = initialise_qc_column(df, qc_column)
    df = df.with_columns(
        pl.when(operator_expr)
        .then(pl.col(flag_column).add(flag_value))
        .otherwise(pl.col(flag_column))
        .alias(flag_column)
    )

    return df


def get_site_range_values(site_id: str, variable: str, resolution: str) -> tuple[float, float]:
    """Get the site-specific minimum and maximum values for range check for a given site, column and resolution.

    This function searches through the site-specific range thresholds and returns the min and max values for
    a given site and resolution. If no specific values are found, it returns the default values for that column
    and resolution.

    Args:
        site_id: Site ID for which range values are needed
        variable: The variable name for which range values are needed
        resolution: The temporal resolution for which range values are needed

    Returns:
        A tuple containing the minimum and maximum values for the range check.
    """
    range_thresholds = get_qc_config("range_thresholds")
    range_threshold = range_thresholds.get(variable)
    if range_threshold is None:
        raise UserWarning(f"No {variable} range thresholds provided.")

    # Get the default values for the given resolution
    default_range_values = next(
        (
            range_thresh
            for range_thresh in range_threshold.defaults
            if range_thresh.resolutions is None or resolution in range_thresh.resolutions
        ),
        None,
    )

    # Get the site specific values for the given site and resolution, defaulting to default values if not found
    range_values = next(
        (
            range_thresh
            for range_thresh in range_threshold.sites
            if range_thresh.site_id == site_id
            and (range_thresh.resolutions is None or resolution in range_thresh.resolutions)
        ),
        default_range_values,
    )

    if range_values is None:
        raise ValueError(f"No min/max values set for {variable} range test")

    return range_values.min_value, range_values.max_value


def initialise_qc_column(df: pl.DataFrame, column: str) -> tuple[pl.DataFrame, str]:
    """Initialise a QC flag column in the DataFrame if it doesn't already exist.

    Args:
        df: The DataFrame to operate on.
        column: The name of the column for which the QC flag column should be checked/created.

    Returns:
        A tuple containing the updated DataFrame and the name of the QC flag column.
    """
    if df.is_empty():
        raise UserWarning("Cannot initialise QC column on empty DataFrame")

    qc_column = f"{column}_QCFLAG"
    if qc_column not in df.columns:
        df = df.with_columns(
            pl.lit(0, dtype=pl.Int64).alias(qc_column)  # TODO: Get this 0 value from somewhere
        )
    return df, qc_column
