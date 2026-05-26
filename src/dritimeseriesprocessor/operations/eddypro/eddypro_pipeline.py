"""End-to-end EddyPro processing pipeline.

Orchestrates the complete EddyPro workflow for a single site:
  1. Write EddyPro project (.eddypro) and instrument (.metadata) config files.
  2. Run eddypro_rp then eddypro_fcc via EddyProRunner.
  3. Parse the EddyPro output CSVs and return the merged DataFrame in memory.
"""

import logging
import tempfile
from datetime import date
from pathlib import Path

import polars as pl

from dritimeseriesprocessor import PACKAGE_ROOT
from dritimeseriesprocessor.models.domain_models.processing_config import DataProcessingConfig
from dritimeseriesprocessor.models.domain_models.site_metadata import SiteMetadata
from dritimeseriesprocessor.models.domain_models.time_series_container import TimeSeriesContainer
from dritimeseriesprocessor.operations.eddypro.eddypro_ancillary_builder import (
    EddyProBiometBuilder,
    EddyProDynamicMetadataBuilder,
)
from dritimeseriesprocessor.operations.eddypro.eddypro_config_builder import EddyProConfigBuilder
from dritimeseriesprocessor.operations.eddypro.eddypro_metadata_mapper import EddyProMetadataMapper
from dritimeseriesprocessor.operations.eddypro.eddypro_runner import EddyProRunner
from dritimeseriesprocessor.utils.strings import extract_uri_id

logger = logging.getLogger(__name__)

_TEMPLATES_DIR = PACKAGE_ROOT / "__assets__" / "eddypro_templates"
_PROJECT_TEMPLATE = _TEMPLATES_DIR / "processing_template.eddypro"
_METADATA_TEMPLATE = _TEMPLATES_DIR / "metadata_template.metadata"


def _read_eddypro_csv(path: Path, header_line: int, data_skip_rows: int) -> pl.DataFrame:
    """Read one EddyPro output CSV, using an explicit header line and skip count.

    Args:
        path: Path to the CSV file.
        header_line: 0-based line index of the column-name row.
        data_skip_rows: Number of lines to skip before the data rows begin.
    """
    with open(path) as f:
        lines = f.readlines()

    raw_header = lines[header_line].strip().split(",")
    header = [col.strip().strip('"') for col in raw_header]

    # Deduplicate column names to avoid Polars concat errors
    seen: dict[str, int] = {}
    unique_header: list[str] = []
    for col in header:
        if col in seen:
            seen[col] += 1
            unique_header.append(f"{col}_{seen[col]}")
        else:
            seen[col] = 0
            unique_header.append(col)

    return pl.read_csv(
        path,
        skip_rows=data_skip_rows,
        has_header=False,
        new_columns=unique_header,
        null_values=["NA", "NAN", "NaN", "-9999", ""],
        infer_schema_length=10000,
        ignore_errors=True,
    )


def _concat_eddypro_csvs(files: list[Path], header_line: int, data_skip_rows: int) -> pl.DataFrame:
    """Concatenate multiple EddyPro CSV files sharing the same format."""
    frames = [_read_eddypro_csv(f, header_line, data_skip_rows) for f in files]
    return pl.concat(frames, how="diagonal_relaxed")


def _add_datetime(df: pl.DataFrame) -> pl.DataFrame:
    """Construct a DateTime column from the 'date' and 'time' string columns."""
    return df.with_columns(
        pl.concat_str([pl.col("date").cast(pl.String), pl.lit(" "), pl.col("time").cast(pl.String)])
        .str.strptime(pl.Datetime, "%Y-%m-%d %H:%M", strict=False)
        .alias("DateTime")
    ).drop(["date", "time"])


def _parse_eddypro_output(output_dir: Path) -> pl.DataFrame:
    """Parse EddyPro full_output, qc_details, and biomet CSVs from output_dir.

    File format conventions (from qc_flux_funcs_python.py):
    - full_output / qc_details: line 1 = column names, line 2 = units, line 3+ = data
    - biomet: line 0 = column names, line 1 = units, line 2+ = data

    Args:
        output_dir: Directory containing EddyPro output files.

    Returns:
        Merged Polars DataFrame with flux, QC flag, and biomet columns.

    Raises:
        FileNotFoundError: If no full_output files are present in output_dir.
    """
    full_output_files = sorted(output_dir.rglob("*full_output*"))
    qc_files = sorted(output_dir.rglob("*qc_details*"))
    biomet_files = sorted(output_dir.rglob("*biomet*"))

    if not full_output_files:
        raise FileNotFoundError(f"No full_output files found in {output_dir}")

    # full_output: header on line 1, data from line 3 (skip_rows=3)
    full_output = _concat_eddypro_csvs(full_output_files, header_line=1, data_skip_rows=3)
    full_output = _add_datetime(full_output)
    full_output = full_output.unique(subset=["DateTime"], keep="first")

    # qc_details: same structure as full_output; keep only QC flag columns
    if qc_files:
        qc_data = _concat_eddypro_csvs(qc_files, header_line=1, data_skip_rows=3)
        qc_data = _add_datetime(qc_data)
        qc_cols = [c for c in qc_data.columns if c.startswith("qc_")]
        if qc_cols:
            qc_data = qc_data.select(["DateTime", *qc_cols])
            full_output = full_output.join(qc_data, on="DateTime", how="left")

    # biomet: header on line 0, data from line 2 (skip_rows=2)
    if biomet_files:
        biomet = _concat_eddypro_csvs(biomet_files, header_line=0, data_skip_rows=2)
        biomet = _add_datetime(biomet)
        # Keep only DateTime and columns not already in full_output
        biomet_cols = ["DateTime"] + [c for c in biomet.columns if c not in full_output.columns]
        full_output = full_output.join(biomet.select(biomet_cols), on="DateTime", how="left")

    # Normalise time column to "time" for consistency with the rest of the pipeline
    full_output = full_output.rename({"DateTime": "time"})

    # EddyPro labels each flux at the END of its 30-min averaging window.
    # The rest of the pipeline uses start-of-period timestamps, so shift back 30 min.
    full_output = full_output.with_columns((pl.col("time") - pl.duration(minutes=30)).alias("time"))

    return full_output


class EddyProPipeline:
    """Orchestrates the full EddyPro processing flow for a single site."""

    def __init__(
        self,
        runner: EddyProRunner,
        config_builder_cls: type[EddyProConfigBuilder] = EddyProConfigBuilder,
    ) -> None:
        self._runner = runner
        self._config_builder_cls = config_builder_cls

    def run(
        self,
        raw_data_dir: Path,
        method_config: DataProcessingConfig,
        site_metadata: SiteMetadata,
        start_date: date,
        end_date: date,
        ancillary_containers: list[TimeSeriesContainer] | None,
    ) -> pl.DataFrame:
        """Execute one EddyPro run and return the parsed output as a DataFrame.

        Args:
            raw_data_dir: Directory containing locally staged raw .dat files.
            method_config: EddyPro processing configuration for this dataset.
            site_metadata: Site-level metadata used to derive the EddyPro run spec.
            start_date: Start of the processing window (inclusive).
            end_date: End of the processing window (inclusive).
            ancillary_containers: Loaded ancillary containers (biomet, dynamic metadata).

        Returns:
            Merged Polars DataFrame of EddyPro full_output, qc_details, and biomet
            output files.
        """
        run_spec = EddyProMetadataMapper().build_run_spec(method_config, site_metadata)
        site_id = run_spec.site_code or (site_metadata.alt_id or extract_uri_id(site_metadata.site_id))
        config_builder = self._config_builder_cls(run_spec=run_spec)

        with tempfile.TemporaryDirectory(prefix=f"eddypro_{site_id}_") as tmpdir:
            working_dir = Path(tmpdir)
            logger.info("EddyPro working directory: %s", working_dir)

            config_dir = working_dir / "config"
            output_dir = working_dir / "output"
            inputs_dir = working_dir / "inputs"
            config_dir.mkdir(parents=True, exist_ok=True)
            output_dir.mkdir(parents=True, exist_ok=True)
            inputs_dir.mkdir(parents=True, exist_ok=True)

            # biomet is required - propagate any failure so the run is aborted.
            biomet_path = EddyProBiometBuilder().build(
                containers=ancillary_containers or [],
                output_path=inputs_dir / "biomet.csv",
            )

            # dynamic metadata is optional - some sites may not have time-varying instrument metadata
            dynamic_metadata_path = None
            if ancillary_containers:
                try:
                    dynamic_metadata_path = EddyProDynamicMetadataBuilder().build(
                        containers=ancillary_containers,
                        output_path=inputs_dir / "dynamic_metadata.txt",
                    )
                except Exception:
                    logger.warning(
                        "Failed to build EddyPro dynamic_metadata.txt for site %s; "
                        "continuing without dynamic metadata.",
                        site_id,
                    )

            project_file = config_builder.build_project_file(
                template_path=_PROJECT_TEMPLATE,
                working_dir=config_dir,
                raw_data_dir=raw_data_dir,
                output_dir=output_dir,
                start_date=start_date,
                end_date=end_date,
                biomet_file=biomet_path,
                dynamic_metadata_file=dynamic_metadata_path,
            )
            config_builder.build_metadata_file(
                template_path=_METADATA_TEMPLATE,
                working_dir=config_dir,
                start_date=start_date,
                end_date=end_date,
            )

            logger.info("Running EddyPro for site %s (window: %s to %s)", site_id, start_date, end_date)
            result = self._runner.run(project_file=project_file, output_dir=output_dir)
            logger.info(
                "EddyPro completed for site %s (rp=%d, fcc=%d)",
                site_id,
                result.return_code_rp,
                result.return_code_fcc,
            )

            # Parse output CSVs into a single DataFrame in memory
            df = _parse_eddypro_output(result.output_dir)

        logger.info("EddyPro pipeline complete for site %s", site_id)
        return df
