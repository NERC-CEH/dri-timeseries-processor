import logging

import polars as pl

logger = logging.getLogger(__name__)


def multiply(df: pl.DataFrame, column: str, correction_factor: float, mask: pl.Expr = pl.lit(True)) -> pl.DataFrame:
    """Applies a multiplication correction to a specific column in the DataFrame based on a condition.

    Args:
        df: The input DataFrame.
        column: The name of the column to correct.
        correction_factor: The factor to multiply the column by.
        mask: The condition to apply for the correction. Default is an expression that defaults to True
            so that expression happens on full DataFrame.

    Returns:
        The DataFrame with the applied correction.
    """

    def _multiply() -> pl.Expr:
        return pl.col(column).mul(correction_factor)

    corrected = df.with_columns(
        pl.when(mask).then(_multiply()).otherwise(pl.col(column)).alias(column),
    )

    return corrected


def add(df: pl.DataFrame, column: str, correction_factor: float, mask: pl.Expr = pl.lit(True)) -> pl.DataFrame:
    """Applies an addition correction to a specific column in the DataFrame based on a condition.

    Args:
        df: The input DataFrame.
        column: The name of the column to correct.
        correction_factor: The factor to add to the column.
        mask: The condition to apply for the correction. Default is an expression that defaults to True
            so that expression happens on full DataFrame.

    Returns:
        The DataFrame with the applied correction.
    """

    def _add() -> pl.Expr:
        return pl.col(column).add(correction_factor)

    corrected = df.with_columns(pl.when(mask).then(_add()).otherwise(pl.col(column)).alias(column))

    return corrected


def power(df: pl.DataFrame, column: str, correction_factor: int, mask: pl.Expr = pl.lit(True)) -> pl.DataFrame:
    """Applies a power correction to a specific column in the DataFrame based on a condition.

    Args:
        df: The input DataFrame.
        column: The name of the column to correct.
        correction_factor: The factor to raise the column to the power of.
        mask: The condition to apply for the correction. Default is an expression that defaults to True
            so that expression happens on full DataFrame.

    Returns:
        The DataFrame with the applied correction.
    """

    def _power() -> pl.Expr:
        return pl.col(column).pow(correction_factor)

    corrected = df.with_columns(pl.when(mask).then(_power()).otherwise(pl.col(column)).alias(column))

    return corrected


def lw(df: pl.DataFrame, column: str, correction_factor: float, mask: pl.Expr = pl.lit(True)) -> pl.DataFrame:
    """Placeholder for LW correction function"""
    return df


def pa(df: pl.DataFrame, column: str, correction_factor: float, mask: pl.Expr = pl.lit(True)) -> pl.DataFrame:
    """Placeholder for PA correction function"""
    return df


def wd(df: pl.DataFrame, column: str, correction_factor: float, mask: pl.Expr = pl.lit(True)) -> pl.DataFrame:
    """Placeholder for WD correction function"""
    return df
