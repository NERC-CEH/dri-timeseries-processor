"""End-to-end EddyPro processing pipeline.

Orchestrates the complete EddyPro workflow for a single site:
  1. Write EddyPro project (.eddypro) and instrument (.metadata) config files.
  2. Run eddypro_rp then eddypro_fcc via EddyProRunner.
  3. Upload raw EddyPro output directory to S3 for archival.
"""

import logging
import tempfile
from datetime import date
from pathlib import Path

from dritimeseriesprocessor import PACKAGE_ROOT
from dritimeseriesprocessor.io_backend.flux_io import FluxS3Client
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
        flux_s3_client: FluxS3Client,
        network: str,
        processed_source_bucket: str,
        processed_dataset: str,
    ) -> None:
        """Execute one EddyPro run from staged raw data and ancillary inputs.

        Args:
            raw_data_dir: Directory containing locally staged raw .dat files.
            method_config: EddyPro processing configuration for this dataset.
            site_metadata: Site-level metadata used to derive the EddyPro run spec.
            start_date: Start of the processing window (inclusive).
            end_date: End of the processing window (inclusive).
            ancillary_containers: Loaded ancillary containers (biomet, dynamic metadata).
            flux_s3_client: S3 client used to upload EddyPro output files.
            network: Network identifier used when constructing the S3 output key.
            processed_source_bucket: S3 bucket to write EddyPro outputs to.
            processed_dataset: Dataset name used when constructing the S3 output key.
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

            # biomet is required — propagate any failure so the run is aborted.
            biomet_path = EddyProBiometBuilder().build(
                containers=ancillary_containers or [],
                output_path=inputs_dir / "biomet.csv",
            )

            # dynamic metadata is optional — some sites may not have time-varying instrument metadata
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

            flux_s3_client.upload_output_files(
                bucket=processed_source_bucket,
                output_dir=result.output_dir,
                network=network,
                site=extract_uri_id(site_metadata.site_id),
                processed_dataset=processed_dataset,
                start_date=start_date,
            )

            logger.info("EddyPro pipeline complete for site %s", site_id)
