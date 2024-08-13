import logging

import polars as pl

from dritimeseriesprocessor.__metadata__.config_preprocessing import Correction

logger = logging.getLogger(__name__)


def multiply(df: pl.DataFrame, mask: pl.expr, config: Correction) -> pl.DataFrame:
    """Applies a multiplication correction to a specific column in the DataFrame based on a condition.

    Args:
        df: The input DataFrame.
        mask: The condition to apply for the correction.
        config: A configuration object containing the correction parameters.

    Returns:
        The DataFrame with the applied correction.
    """

    def _multiply() -> pl.Expr:
        return pl.col(config.VARIABLE).mul(config.CORRECTION_FACTOR)

    corrected = _when_then_wrapper(df, when=mask, then=_multiply(), otherwise=pl.col(config.VARIABLE))
    return corrected


def add(df: pl.DataFrame, mask: pl.Expr, config: Correction) -> pl.DataFrame:
    """Applies an addition correction to a specific column in the DataFrame based on a condition.

    Args:
        df: The input DataFrame.
        mask: The condition to apply for the correction.
        config: A configuration object containing the correction parameters.

    Returns:
        The DataFrame with the applied correction.
    """

    def _add() -> pl.Expr:
        return pl.col(config.VARIABLE).add(config.CORRECTION_FACTOR)

    corrected = _when_then_wrapper(df, when=mask, then=_add(), otherwise=pl.col(config.VARIABLE))
    return corrected


def _when_then_wrapper(df: pl.DataFrame, when: pl.Expr, then: pl.Expr, otherwise: pl.Expr) -> pl.DataFrame:
    """Wraps the Polars `when().then().otherwise()` logic into a reusable function.

    Args:
        df: The DataFrame to operate on.
        when: The condition to evaluate.
        then: The expression to apply when the condition is true.
        otherwise: The expression to apply when the condition is false.

    Returns:
        The DataFrame with the applied conditional logic.
    """
    return df.with_columns(pl.when(when).then(then).otherwise(otherwise))


preprocessing_operations = {"MULTIPLY": multiply, "ADD": add}
