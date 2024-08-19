import logging

import polars as pl

from dritimeseriesprocessor.__metadata__.config_preprocessing import Correction

logger = logging.getLogger(__name__)


def multiply(df: pl.DataFrame, config: Correction, mask: pl.Expr = pl.lit(True)) -> pl.DataFrame:
    """Applies a multiplication correction to a specific column in the DataFrame based on a condition.

    Args:
        df: The input DataFrame.
        config: A configuration object containing the correction parameters.
        mask: The condition to apply for the correction. Default is an expression that defaults to True
              so that expression happens on full DataFrame.

    Returns:
        The DataFrame with the applied correction.
    """

    def _multiply() -> pl.Expr:
        return pl.col(config.VARIABLE).mul(config.CORRECTION_FACTOR)

    corrected = df.with_columns(pl.when(mask).then(_multiply()).otherwise(pl.col(config.VARIABLE)))

    return corrected


def add(df: pl.DataFrame, config: Correction, mask: pl.Expr = pl.lit(True)) -> pl.DataFrame:
    """Applies an addition correction to a specific column in the DataFrame based on a condition.

    Args:
        df: The input DataFrame.
        config: A configuration object containing the correction parameters.
        mask: The condition to apply for the correction. Default is an expression that defaults to True
              so that expression happens on full DataFrame.

    Returns:
        The DataFrame with the applied correction.
    """

    def _add() -> pl.Expr:
        return pl.col(config.VARIABLE).add(config.CORRECTION_FACTOR)

    corrected = df.with_columns(pl.when(mask).then(_add()).otherwise(pl.col(config.VARIABLE)))

    return corrected


preprocessing_corrections = {"MULTIPLY": multiply, "ADD": add}
