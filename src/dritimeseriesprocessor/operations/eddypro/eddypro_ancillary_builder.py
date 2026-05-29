"""Build EddyPro ancillary input files from already-loaded DAG dependencies."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from pathlib import Path

import polars as pl

from dritimeseriesprocessor.models.domain_models.time_series_container import TimeSeriesContainer

logger = logging.getLogger(__name__)


def _accumulate_into_frame(
    containers: list[TimeSeriesContainer],
    source_order: Sequence[str],
) -> tuple[pl.DataFrame, list[str]]:
    """Join supported container series on a shared EddyPro DateTime axis."""
    df: pl.DataFrame | None = None
    requested: list[str] = []
    for c in containers:
        if not c.source_column or c.source_column not in source_order:
            continue
        source_col = c.source_column
        if source_col not in requested:
            requested.append(source_col)
        if c.data is None:
            continue

        time_col = c.time_column_name
        src = c.data.df
        if time_col not in src.columns or source_col not in src.columns:
            continue
        if df is not None and source_col in df.columns:
            continue

        series = (
            src.select(
                pl.col(time_col).cast(pl.Datetime).alias("DateTime"),
                pl.col(source_col).cast(pl.Float64, strict=False).alias(source_col),
            )
            .drop_nulls("DateTime")
            .unique(subset=["DateTime"], keep="first")
            .sort("DateTime")
        )
        if df is None:
            df = series
        else:
            df = df.join(series, on="DateTime", how="full", coalesce=True).sort("DateTime")

    if df is None:
        df = pl.DataFrame({"DateTime": pl.Series([], dtype=pl.Datetime)})

    return df, requested


class EddyProBiometBuilder:
    """Build a `biomet.csv` file from a set of already-loaded PT30M ancillary containers.

    Iterates over the supplied containers, selects those whose source column is a
    recognised biomet variable, joins them on a shared DateTime axis, and writes the
    result in the two-row-header CSV format expected by EddyPro's external biomet
    input (`use_biom=2`).
    """

    # Keep deterministic source-column order so EddyPro's fixed `biom_*` indices
    # continue to point at the intended columns without renaming the headers.
    _SOURCE_ORDER: list[str] = [
        "AirTemp_C",
        "RH",
        "Pressure_Avg",
        "R_SW_in_Avg",
        "T_nr_Avg",
        "G_PLATE_1_1_1",
        "G_PLATE_1_1_2",
    ]

    def build(
        self,
        containers: list[TimeSeriesContainer],
        output_path: Path,
    ) -> Path:
        """Write EddyPro biomet CSV (header + units row + data rows) to output_path.

        Args:
            containers: Ancillary containers to inspect. Only those whose
                source_column is in _SOURCE_ORDER contribute data; others are ignored.
            output_path: Destination path for the biomet CSV file.

        Returns:
            Path to the written file.

        Raises:
            ValueError: If no usable biomet data exists across the supplied containers
                for the current run window.

        Notes:
            EddyPro consumes this file when `use_biom=2` is set in the project config.
            Input containers are expected to have already been aggregated to PT30M by
            the normal timeseries aggregation pathway.
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)

        df, requested = _accumulate_into_frame(containers, self._SOURCE_ORDER)
        requested_set = {name for name in requested if name}
        ordered_value_cols = [name for name in self._SOURCE_ORDER if name in requested_set]
        ordered_value_cols.extend(sorted(requested_set.difference(self._SOURCE_ORDER)))

        # Ensure all requested output columns exist even if source data are missing.
        missing = [name for name in ordered_value_cols if name not in df.columns]
        if missing:
            df = df.with_columns([pl.lit(None).cast(pl.Float64).alias(name) for name in missing])

        if not ordered_value_cols or not any(
            df[col].drop_nulls().len() > 0 for col in ordered_value_cols if col in df.columns
        ):
            raise ValueError(
                f"No usable biomet data found for the current run window. Requested columns: {ordered_value_cols}"
            )

        df = df.drop_nulls(ordered_value_cols)
        df = df.with_columns([pl.col(name).round(2).alias(name) for name in ordered_value_cols])

        df = df.with_columns(pl.col("DateTime").dt.strftime("%Y-%m-%d %H:%M").alias("TIMESTAMP_1")).sort("DateTime")
        ordered_cols = ["TIMESTAMP_1", *ordered_value_cols]
        header_row = ",".join(ordered_cols)
        units_row = ",".join(["yyyy-mm-dd HH:MM", *["-" for _ in ordered_value_cols]])
        data_df = df.select([pl.col(name) for name in ordered_cols])

        with open(output_path, "w") as f:
            f.write(header_row + "\n")
            f.write(units_row + "\n")
            for row in data_df.iter_rows():
                f.write(",".join("" if v is None else str(v) for v in row) + "\n")

        logger.info("Wrote EddyPro biomet file: %s", output_path)
        return output_path


class EddyProDynamicMetadataBuilder:
    """Build a `dynamic_metadata.txt` file from a set of already-loaded FLUX_METADATA containers.

    Iterates over the supplied containers, selects those whose source column is a
    recognised dynamic metadata variable, joins them on a shared DateTime axis, and
    writes the result in the tab-separated format expected by EddyPro's dynamic
    metadata input. Rows where all value columns are null are dropped; partial rows
    (at least one non-null value) are preserved.
    """

    _SOURCE_ORDER: list[str] = ["sonic_azimuth", "height_measurement", "height_canopy"]
    _UNITS: dict[str, str] = {
        "sonic_azimuth": "deg",
        "height_measurement": "m",
        "height_canopy": "m",
    }

    def build(
        self,
        containers: list[TimeSeriesContainer],
        output_path: Path,
    ) -> Path | None:
        """Write EddyPro dynamic metadata file (header + units row + data rows) to output_path.

        Args:
            containers: Ancillary containers to inspect. Only those whose
                source_column is in _SOURCE_ORDER contribute data; others are ignored.
            output_path: Destination path for the dynamic metadata file.

        Returns:
            Path to the written file, or None if no usable dynamic metadata exists
            across the supplied containers for the current run window.
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)

        df, requested = _accumulate_into_frame(containers, self._SOURCE_ORDER)
        requested_set = {name for name in requested if name}
        ordered_value_cols = [name for name in self._SOURCE_ORDER if name in requested_set]
        ordered_value_cols.extend(sorted(requested_set.difference(self._SOURCE_ORDER)))

        missing = [name for name in ordered_value_cols if name not in df.columns]
        if missing:
            df = df.with_columns([pl.lit(None).cast(pl.Float64).alias(name) for name in missing])

        if not ordered_value_cols or not any(
            df[col].drop_nulls().len() > 0 for col in ordered_value_cols if col in df.columns
        ):
            logger.warning(
                "No usable dynamic metadata found for the current run window; skipping dynamic_metadata.txt. "
                f"Requested columns: {ordered_value_cols}"
            )
            return None

        # Drop only rows where ALL value columns are null - preserve partial rows.
        if ordered_value_cols:
            all_null = pl.all_horizontal(pl.col(c).is_null() for c in ordered_value_cols)
            df = df.filter(~all_null)

        df = df.with_columns(
            pl.col("DateTime").dt.strftime("%Y-%m-%d").alias("date"),
            pl.col("DateTime").dt.strftime("%H:%M").alias("time"),
        ).sort("DateTime")

        ordered_cols = ["date", "time", *ordered_value_cols]
        header_row = "\t".join(ordered_cols)
        units_row = "\t".join(["yyyy-mm-dd", "HH:MM", *[self._UNITS.get(name, "-") for name in ordered_value_cols]])
        data_df = df.select([pl.col(name) for name in ordered_cols])

        with open(output_path, "w") as f:
            f.write(header_row + "\n")
            f.write(units_row + "\n")
            for row in data_df.iter_rows():
                f.write("\t".join("" if v is None else str(v) for v in row) + "\n")

        logger.info("Wrote EddyPro dynamic metadata file: %s", output_path)
        return output_path
