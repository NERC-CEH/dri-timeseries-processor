"""End-to-end EddyPro processing pipeline.

Orchestrates: config generation -> binary execution -> output collection.
"""

import logging
import shutil
from datetime import date
from pathlib import Path

from dritimeseriesprocessor.operations.eddypro.eddypro_config_builder import EddyProConfigBuilder
from dritimeseriesprocessor.operations.eddypro.eddypro_runner import EddyProResult, EddyProRunner

logger = logging.getLogger(__name__)


class EddyProPipeline:
    """Orchestrates the full EddyPro processing flow.

    Steps:
      1. Create working subdirectories (config/, output/)
      2. Build the .eddypro project file from the template
      3. Copy the .metadata file from the template
      4. Copy biomet and dynamic metadata files if provided
      5. Run eddypro_rp and eddypro_fcc
      6. Return the result (output lives in output_dir)
    """

    def __init__(
        self,
        runner: EddyProRunner,
        config_builder: EddyProConfigBuilder,
        project_template: Path,
        metadata_template: Path,
    ) -> None:
        self._runner = runner
        self._config_builder = config_builder
        self._project_template = project_template
        self._metadata_template = metadata_template

    def run(
        self,
        raw_data_dir: Path,
        working_dir: Path,
        start_date: date,
        end_date: date,
        biomet_file: Path | None = None,
        dynamic_metadata_file: Path | None = None,
    ) -> EddyProResult:
        """Run the full EddyPro processing pipeline.

        Args:
            raw_data_dir: Directory containing raw .dat files.
            working_dir: Base working directory for this run.
            start_date: Processing window start date.
            end_date: Processing window end date.
            biomet_file: Optional path to biomet CSV file.
            dynamic_metadata_file: Optional path to dynamic metadata file.

        Returns:
            EddyProResult with return codes, captured output, and output directory.
        """
        config_dir = working_dir / "config"
        output_dir = working_dir / "output"
        config_dir.mkdir(parents=True, exist_ok=True)
        output_dir.mkdir(parents=True, exist_ok=True)

        logger.info("EddyPro pipeline starting: working_dir=%s", working_dir)

        # Prepare optional ancillary files in the config directory
        local_biomet = None
        if biomet_file:
            local_biomet = config_dir / biomet_file.name
            shutil.copy2(biomet_file, local_biomet)
            logger.info("Copied biomet file to: %s", local_biomet)

        local_dynamic_metadata = None
        if dynamic_metadata_file:
            local_dynamic_metadata = config_dir / dynamic_metadata_file.name
            shutil.copy2(dynamic_metadata_file, local_dynamic_metadata)
            logger.info("Copied dynamic metadata file to: %s", local_dynamic_metadata)

        # Build project and metadata files
        project_file = self._config_builder.build_project_file(
            template_path=self._project_template,
            working_dir=config_dir,
            raw_data_dir=raw_data_dir,
            output_dir=output_dir,
            start_date=start_date,
            end_date=end_date,
            biomet_file=local_biomet,
            dynamic_metadata_file=local_dynamic_metadata,
        )

        self._config_builder.build_metadata_file(
            template_path=self._metadata_template,
            working_dir=config_dir,
            start_date=start_date,
            end_date=end_date,
        )

        # Run EddyPro (rp then fcc)
        result = self._runner.run(
            project_file=project_file,
            output_dir=output_dir,
        )

        logger.info("EddyPro pipeline completed: rp=%d, fcc=%d", result.return_code_rp, result.return_code_fcc)
        return result
