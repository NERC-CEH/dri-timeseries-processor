"""EddyPro configuration builder for generating run-specific project files.

Reads template .eddypro and .metadata INI files, overwrites only the
dynamic fields (paths, dates, site-specific values), and writes the
modified files to a working directory.
"""

import configparser
import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class EddyProSiteConfig:
    """Site-specific configuration for EddyPro processing.

    Contains values that change per-site and are injected into the
    template .eddypro project file.

    Note: canopy_height is NOT included here — it comes from the
    dynamic_metadata.txt file which EddyPro reads directly.
    """

    site_id: str
    latitude: float
    longitude: float
    altitude: float
    file_prototype: str
    canopy_height: float | None = None
    displacement_height: float | None = None
    roughness_length: float | None = None


class EddyProConfigBuilder:
    """Builds run-specific EddyPro project files from templates."""

    EDDYPRO_HEADER = ";EDDYPRO_PROCESSING"
    METADATA_HEADER = ";GHG_METADATA"

    def __init__(self, site_config: EddyProSiteConfig) -> None:
        self._site_config = site_config

    def build_project_file(
        self,
        template_path: Path,
        working_dir: Path,
        raw_data_dir: Path,
        output_dir: Path,
        start_date: date,
        end_date: date,
        biomet_file: Path | None = None,
        dynamic_metadata_file: Path | None = None,
    ) -> Path:
        """Read template .eddypro file and overwrite dynamic fields for this run.

        Args:
            template_path: Path to the template .eddypro file.
            working_dir: Working directory for this run.
            raw_data_dir: Directory containing raw .dat files.
            output_dir: Directory where EddyPro should write output.
            start_date: Processing start date.
            end_date: Processing end date.
            biomet_file: Optional path to biomet file.
            dynamic_metadata_file: Optional path to dynamic metadata file.

        Returns:
            Path to the written processing.eddypro file.
        """
        config = self._read_eddypro_ini(template_path)

        working_dir.mkdir(parents=True, exist_ok=True)
        output_file = working_dir / "processing.eddypro"

        # [Project] section — run-specific paths and dates
        config.set("Project", "project_id", self._site_config.site_id)
        config.set("Project", "file_name", str(output_file))
        config.set("Project", "out_path", str(output_dir))
        config.set("Project", "file_prototype", self._site_config.file_prototype)
        config.set("Project", "pr_start_date", start_date.strftime("%Y-%m-%d"))
        config.set("Project", "pr_end_date", end_date.strftime("%Y-%m-%d"))
        config.set("Project", "pr_start_time", "00:00")
        config.set("Project", "pr_end_time", "23:59")

        # Metadata file reference (will be written alongside this file)
        metadata_file = working_dir / f"{self._site_config.site_id}.metadata"
        config.set("Project", "proj_file", str(metadata_file))

        if dynamic_metadata_file:
            config.set("Project", "use_dyn_md_file", "1")
            config.set("Project", "dyn_metadata_file", str(dynamic_metadata_file))

        if biomet_file:
            config.set("Project", "biom_file", str(biomet_file))

        # [RawProcess_General] section — data path
        config.set("RawProcess_General", "data_path", str(raw_data_dir))

        self._write_eddypro_ini(config, output_file, self.EDDYPRO_HEADER)

        logger.info("Built EddyPro project file: %s", output_file)
        return output_file

    def build_metadata_file(
        self,
        template_path: Path,
        working_dir: Path,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> Path:
        """Write a site-specific metadata file to the working directory.

        Populates core site fields (lat/lon/altitude, canopy height etc) so EddyPro
        doesn't default them to zero.

        Args:
            template_path: Path to the template .metadata file.
            working_dir: Working directory for this run.
            start_date: Optional processing window start date.
            end_date: Optional processing window end date.

        Returns:
            Path to the written metadata file.
        """
        working_dir.mkdir(parents=True, exist_ok=True)
        output_file = working_dir / f"{self._site_config.site_id}.metadata"

        config = self._read_eddypro_ini(template_path)

        if config.has_section("Project"):
            config.set("Project", "id", self._site_config.site_id)
            config.set("Project", "file_name", str(output_file))
            if start_date:
                config.set("Project", "start_date", start_date.strftime("%Y-%m-%d"))
            if end_date:
                config.set("Project", "end_date", end_date.strftime("%Y-%m-%d"))

        if config.has_section("Site"):
            config.set("Site", "site_name", self._site_config.site_id)
            config.set("Site", "site_id", self._site_config.site_id)
            config.set("Site", "altitude", f"{self._site_config.altitude}")
            config.set("Site", "latitude", f"{self._site_config.latitude}")
            config.set("Site", "longitude", f"{self._site_config.longitude}")
            if self._site_config.canopy_height is not None:
                config.set("Site", "canopy_height", f"{self._site_config.canopy_height}")
            if self._site_config.displacement_height is not None:
                config.set("Site", "displacement_height", f"{self._site_config.displacement_height}")
            if self._site_config.roughness_length is not None:
                config.set("Site", "roughness_length", f"{self._site_config.roughness_length}")

        self._write_eddypro_ini(config, output_file, self.METADATA_HEADER)
        logger.info("Copied metadata file to: %s", output_file)
        return output_file

    def _read_eddypro_ini(self, path: Path) -> configparser.ConfigParser:
        """Read an EddyPro INI file, skipping the header comment line."""
        config = configparser.ConfigParser()
        config.optionxform = str  # Preserve case of keys

        text = path.read_text()
        # Strip the header comment line (e.g. ;EDDYPRO_PROCESSING)
        lines = text.splitlines(keepends=True)
        if lines and lines[0].startswith(";"):
            text = "".join(lines[1:])

        config.read_string(text)
        return config

    def _write_eddypro_ini(self, config: configparser.ConfigParser, path: Path, header: str) -> None:
        """Write an EddyPro INI file with the header comment restored."""
        with open(path, "w") as f:
            f.write(header + "\n")
            config.write(f, space_around_delimiters=False)
