from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

import polars as pl
import time_stream as ts

from time_stream.operation import Operation
from time_stream.utils import check_columns_in_dataframe, get_date_filter


@dataclass(frozen=True)
class CorrectionCtx:
    """Immutable context passed to QC checks."""

    df: pl.DataFrame
    time_name: str
    observation_interval: datetime | tuple[datetime, datetime | None] | None = None


class Correction(Operation, ABC):
    """Base class for quality control checks."""

    @abstractmethod
    def _correct(self, _ctx: CorrectionCtx, _column: str) -> pl.DataFrame:
        """Return the Polars dataframe containing corrected data."""
        pass

    def apply(
        self,
        df: pl.DataFrame,
        time_name: str,
        correction_column: str,
        observation_interval: datetime | tuple[datetime, datetime | None] | None = None,
    ) -> pl.DataFrame:
        """Apply the correction to the data.

        Args:
            df: The Polars DataFrame containing the time series data to apply corrections to
            time_name: Name of the time column in the dataframe
            correction_column: The column to perform the correction on.
            observation_interval: Optional time interval to limit the corrections to.

        Returns:
            pl.DataFrame: DataFrame with resolved corrections
        """
        ctx = CorrectionCtx(df, time_name, observation_interval)
        pipeline = CorrectionPipeline(self, ctx, correction_column, observation_interval)
        return pipeline.execute()


class CorrectionPipeline:
    """Encapsulates the logic for the correction pipeline steps."""

    def __init__(
        self,
        correction: Correction,
        ctx: CorrectionCtx,
        column: str,
        observation_interval: datetime | tuple[datetime, datetime | None] | None = None,
    ):
        self.correction = correction
        self.ctx = ctx
        self.column = column
        self.observation_interval = observation_interval

    def execute(self) -> pl.DataFrame:
        """Execute the quality control check pipeline

        Returns:
            Polars DataFrame of the result of the correction
        """
        self._validate()

        # Get the correction expression
        df_corrected = self.correction._correct(self.ctx, self.column)

        # Apply observation interval filter if specified
        filter_expr = get_date_filter(self.ctx.time_name, self.observation_interval)
        df_corrected = df_corrected.with_columns(
            pl.when(filter_expr).then(pl.col(self.column)).otherwise(pl.col(self.column)).alias(self.column)
        )

        return df_corrected

    def _validate(self) -> None:
        """Carry out validation that the correction can actually be carried out."""
        if self.ctx.df.is_empty():
            raise ValueError("Cannot perform correction on an empty DataFrame.")
        check_columns_in_dataframe(self.ctx.df, [self.column, self.ctx.time_name])


@Correction.register
class Scalar(Correction):
    """Scalar operation class."""

    name = "scalar"

    def __init__(self, correction_factor: float) -> None:
        """Initialise the Scale operation with a correction factor.

        Args:
            correction_factor: The factor to scale the column by.
        """
        self.correction_factor = correction_factor

    def _correct(self, _ctx: CorrectionCtx, _column: str) -> pl.DataFrame:
        """Apply the scalar operation to the DataFrame"""
        corrected = _ctx.df.with_columns(pl.col(_column) * self.correction_factor)
        return corrected


@Correction.register
class Add(Correction):
    """Add operation class."""

    name = "add"

    def __init__(self, correction_factor: float) -> None:
        """Initialise the Add operation with a correction factor.

        Args:
            correction_factor: The factor to add to the column.
        """
        self.correction_factor = correction_factor

    def _correct(self, _ctx: CorrectionCtx, _column: str) -> pl.DataFrame:
        """Apply the add operation to the DataFrame"""
        corrected = _ctx.df.with_columns(pl.col(_column) + self.correction_factor)
        return corrected


@Correction.register
class Power(Correction):
    """Power operation class."""

    name = "power"

    def __init__(self, correction_factor: float) -> None:
        """Initialise the Power operation with a correction factor.

        Args:
            correction_factor: The factor to raise the column to the power of.
        """
        self.correction_factor = correction_factor

    def _correct(self, _ctx: CorrectionCtx, _column: str) -> pl.DataFrame:
        """Apply the power operation to the DataFrame"""
        corrected = _ctx.df.with_columns(pl.col(_column).pow(self.correction_factor))
        return corrected


@Correction.register
class LWCorrection(Correction):
    """Long wave correction operation class."""

    name = "lw_corr"

    def __init__(self, lw_unc: ts.TimeFrame, ta: ts.TimeFrame, correction_factor: float) -> None:
        """Initialise the LW correction operation.

        Args:
            lw_unc: The ts.TimeFrame object containing the uncalibrated long wave radiation data.
            ta: The ts.TimeFrame object containing the air temperature data.
            correction_factor: The factor to multiply the uncalibrated long wave radiation by before re-calibration.

        """
        self.lw_unc = lw_unc
        self.ta = ta
        self.correction_factor = correction_factor

    def _correct(self, _ctx: CorrectionCtx, _column: str) -> pl.DataFrame:
        """Apply the power operation to the DataFrame"""
        lw_unc_col = self.lw_unc.metadata["column_name"]
        ta_col = self.ta.metadata["column_name"]

        # First correct the uncalibrated values with the scalar correction.
        lw_unc_corr = Scalar(self.correction_factor).apply(
            self.lw_unc.df, self.lw_unc.time_name, lw_unc_col, _ctx.observation_interval
        )

        # Now re-calibrate LW value with temperature adjustment.
        # Convert temperature to Kelvin
        ta_k = Add(273.15).apply(self.ta.df, self.ta.time_name, ta_col, _ctx.observation_interval)

        # Get adjustment amount from Stefan-Boltzmann constant 5.67 * 10^-8
        sb_adj = ta_k.with_columns((pl.col(ta_col).pow(4) * 5.67 * 1e-8).alias("SB_adj")).select("SB_adj")

        # Recalculate LW value
        corrected = _ctx.df.with_columns((lw_unc_corr[lw_unc_col] + sb_adj["SB_adj"]).alias(_column))

        return corrected


@Correction.register
class PACorrection(Correction):
    """Correct air pressure with bias calculated from mean sea level pressure."""

    name = "pa_corr"

    def __init__(self, ta: ts.TimeFrame, altitude: float, correction_factor: float) -> None:
        """Initialise the PA correction operation.

        Args:
            ta: ts.TimeFrame object containing the air temperature data.
            altitude: Site altitude in metres.
            correction_factor: The factor used in PA correction.

        """
        self.ta = ta
        self.altitude = altitude
        self.correction_factor = correction_factor

    def _correct(self, _ctx: CorrectionCtx, _column: str) -> pl.DataFrame:
        """Apply the PA correction to the DataFrame."""
        ta_col = self.ta.metadata["column_name"]

        # Using the MSLP to PA conversion factor, calculate the unique adjustments for each PA value.
        pa_corr = self.ta.df.with_columns(
            (
                self.correction_factor
                * (1 - ((0.0065 * self.altitude) / (pl.col(ta_col) + (0.0065 * self.altitude) + 273.15))) ** 5.257
            ).alias("pa_corr")
        )

        corrected = _ctx.df.with_columns(
            (pl.col(_column) + pa_corr["pa_corr"]).alias(_column)
        )

        return corrected


# TODO: Placeholder implementation
@Correction.register
class WDCorrection(Correction):
    """Wind direction correction operation class."""

    name = "wd_corr"

    def __init__(self, ux: ts.TimeFrame, uy: ts.TimeFrame) -> None:
        """Initialise the WD correction operation.

        Args:
            ux: The ts.TimeFrame object containing the u-component of wind data.
            uy: The ts.TimeFrame object containing the y-component of wind data.

        """
        self.ux = ux
        self.uy = uy

    def _correct(self, _ctx: CorrectionCtx, _column: str) -> pl.DataFrame:
        """Apply the PA correction to the DataFrame."""
        return _ctx.df
