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
from dritimeseriesprocessor.operations.eddypro.eddypro_config_builder import EddyProConfigBuilder
from dritimeseriesprocessor.operations.eddypro.eddypro_metadata_mapper import EddyProMetadataMapper
from dritimeseriesprocessor.operations.eddypro.eddypro_runner import EddyProRunner

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
        flux_s3_client: FluxS3Client,
        network: str,
        processed_source_bucket: str,
        processed_dataset: str,
    ) -> None:
        if not site_metadata.alt_id:
            raise ValueError(f"Site metadata missing alt_id (required for EddyPro): {site_metadata.site_id}")
        site_id = site_metadata.alt_id

        run_spec = EddyProMetadataMapper().build_run_spec(method_config, site_metadata)
        config_builder = self._config_builder_cls(run_spec=run_spec)

        with tempfile.TemporaryDirectory(prefix=f"eddypro_{site_id}_") as tmpdir:
            working_dir = Path(tmpdir)
            logger.info("EddyPro working directory: %s", working_dir)

            config_dir = working_dir / "config"
            output_dir = working_dir / "output"
            config_dir.mkdir(parents=True, exist_ok=True)
            output_dir.mkdir(parents=True, exist_ok=True)

            project_file = config_builder.build_project_file(
                template_path=_PROJECT_TEMPLATE,
                working_dir=config_dir,
                raw_data_dir=raw_data_dir,
                output_dir=output_dir,
                start_date=start_date,
                end_date=end_date,
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
                site=site_id,
                processed_dataset=processed_dataset,
                start_date=start_date,
                end_date=end_date,
            )

            logger.info("EddyPro pipeline complete for site %s", site_id)