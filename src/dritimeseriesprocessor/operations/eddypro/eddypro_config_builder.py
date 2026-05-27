"""Build EddyPro config files from the local templates."""

import configparser
import logging
from datetime import date
from pathlib import Path

from dritimeseriesprocessor.operations.eddypro.eddypro_run_spec import EddyProRunSpec

logger = logging.getLogger(__name__)


class EddyProConfigBuilder:
    """Fill the EddyPro project and metadata templates for one run."""

    EDDYPRO_HEADER = ";EDDYPRO_PROCESSING"
    METADATA_HEADER = ";GHG_METADATA"

    def __init__(self, run_spec: EddyProRunSpec) -> None:
        self._run_spec = run_spec

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
        """Write the project file for one run."""
        working_dir.mkdir(parents=True, exist_ok=True)

        site_id = self._run_spec.site_code
        output_file = working_dir / "processing.eddypro"

        config = self._read_ini(template_path)
        start_str = start_date.strftime("%Y-%m-%d")
        end_str = end_date.strftime("%Y-%m-%d")

        config.set("Project", "project_id", site_id)
        config.set("Project", "file_name", str(output_file))
        config.set("Project", "out_path", str(output_dir))
        config.set("Project", "file_prototype", self._run_spec.file_prototype)
        config.set("Project", "pr_start_date", start_str)
        config.set("Project", "pr_end_date", end_str)
        config.set("Project", "pr_start_time", "00:00")
        config.set("Project", "pr_end_time", "23:59")
        config.set("Project", "sw_version", self._run_spec.software_version)

        if self._run_spec.master_sonic:
            config.set("Project", "master_sonic", self._run_spec.master_sonic)

        columns = self._run_spec.columns
        variable_index = {col.variable: i for i, col in enumerate(columns, start=1) if col.variable}
        config.set("Project", "col_diag_anem", str(variable_index.get("anemometer_diagnostic", 0)))
        config.set("Project", "col_co2", str(variable_index.get("co2", 0)))
        config.set("Project", "col_h2o", str(variable_index.get("h2o", 0)))
        config.set("Project", "col_air_t", str(variable_index.get("air_t", 0)))
        config.set("Project", "col_cell_t", str(variable_index.get("cell_t", 0)))
        config.set("Project", "col_int_p", str(variable_index.get("int_p", 0)))
        config.set("Project", "col_air_p", str(variable_index.get("air_p", 0)))

        metadata_file = working_dir / f"{site_id}.metadata"
        config.set("Project", "proj_file", str(metadata_file))

        if dynamic_metadata_file is not None:
            config.set("Project", "use_dyn_md_file", "1")
            config.set("Project", "dyn_metadata_file", str(dynamic_metadata_file))
        else:
            config.set("Project", "use_dyn_md_file", "0")
            config.set("Project", "dyn_metadata_file", "")

        if biomet_file is not None:
            config.set("Project", "use_biom", "2")
            config.set("Project", "biom_file", str(biomet_file))
            if config.has_option("Project", "biom_dir"):
                config.set("Project", "biom_dir", str(biomet_file.parent))
        else:
            config.set("Project", "use_biom", "0")
            config.set("Project", "biom_file", "")
            if config.has_option("Project", "biom_dir"):
                config.set("Project", "biom_dir", "")

        config.set("RawProcess_General", "data_path", str(raw_data_dir))

        for section in ("RawProcess_TiltCorrection_Settings", "RawProcess_TimelagOptimization_Settings"):
            if config.has_section(section):
                config.set(section, "pf_start_date" if "Tilt" in section else "to_start_date", start_str)
                config.set(section, "pf_end_date" if "Tilt" in section else "to_end_date", end_str)

        self._write_ini(config, output_file, self.EDDYPRO_HEADER)
        logger.info("Built EddyPro project file: %s", output_file)
        return output_file

    def build_metadata_file(
        self,
        template_path: Path,
        working_dir: Path,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> Path:
        """Write the site metadata file for one run."""
        working_dir.mkdir(parents=True, exist_ok=True)

        site_id = self._run_spec.site_code
        output_file = working_dir / f"{site_id}.metadata"

        config = self._read_ini(template_path)

        if config.has_section("Project"):
            config.set("Project", "id", site_id)
            config.set("Project", "file_name", str(output_file))
            config.set("Project", "sw_version", self._run_spec.software_version)
            if start_date:
                config.set("Project", "start_date", start_date.strftime("%Y-%m-%d"))
            if end_date:
                config.set("Project", "end_date", end_date.strftime("%Y-%m-%d"))

        if config.has_section("Site"):
            config.set("Site", "site_name", site_id)
            config.set("Site", "site_id", site_id)
            if self._run_spec.altitude is not None:
                config.set("Site", "altitude", str(self._run_spec.altitude))
            if self._run_spec.latitude is not None:
                config.set("Site", "latitude", str(self._run_spec.latitude))
            if self._run_spec.longitude is not None:
                config.set("Site", "longitude", str(self._run_spec.longitude))
            if self._run_spec.canopy_height is not None:
                config.set("Site", "canopy_height", str(self._run_spec.canopy_height))
            if self._run_spec.displacement_height is not None:
                config.set("Site", "displacement_height", str(self._run_spec.displacement_height))
            if self._run_spec.roughness_length is not None:
                config.set("Site", "roughness_length", str(self._run_spec.roughness_length))

        if config.has_section("Timing"):
            if self._run_spec.acquisition_frequency is not None:
                config.set("Timing", "acquisition_frequency", str(self._run_spec.acquisition_frequency))
            if self._run_spec.file_duration is not None:
                config.set("Timing", "file_duration", str(self._run_spec.file_duration))

        instruments = self._run_spec.instruments
        if instruments:
            config.remove_section("Instruments")
            config.add_section("Instruments")
            for idx, inst in enumerate(instruments, start=1):
                for key, value in inst.fields.items():
                    if value is not None:
                        config.set("Instruments", f"instr_{idx}_{key}", str(value))

        columns = self._run_spec.columns
        if columns:
            config.remove_section("FileDescription")
            config.add_section("FileDescription")
            fd = config["FileDescription"]
            fd["separator"] = "comma"
            fd["data_label"] = "Not set"
            fd["header_rows"] = "4"

            for col_idx, col in enumerate(columns, start=1):
                prefix = f"col_{col_idx}_"
                fd[prefix + "variable"] = col.variable
                fd[prefix + "instrument"] = col.instrument
                fd[prefix + "measure_type"] = col.measure_type
                fd[prefix + "unit_in"] = col.unit_in
                fd[prefix + "min_value"] = col.min_value
                fd[prefix + "max_value"] = col.max_value
                fd[prefix + "conversion"] = col.conversion
                fd[prefix + "unit_out"] = col.unit_out
                fd[prefix + "a_value"] = col.a_value
                fd[prefix + "b_value"] = col.b_value
                fd[prefix + "nom_timelag"] = col.nom_timelag
                fd[prefix + "min_timelag"] = col.min_timelag
                fd[prefix + "max_timelag"] = col.max_timelag

        self._write_ini(config, output_file, self.METADATA_HEADER)
        logger.info("Built metadata file: %s", output_file)
        return output_file

    def _read_ini(self, path: Path) -> configparser.ConfigParser:
        config = configparser.ConfigParser()
        config.optionxform = str  # type: ignore
        text = path.read_text()

        lines = text.splitlines(keepends=True)
        if lines and lines[0].startswith(";"):
            text = "".join(lines[1:])
        config.read_string(text)
        return config

    def _write_ini(self, config: configparser.ConfigParser, path: Path, header: str) -> None:
        with open(path, "w") as f:
            f.write(header + "\n")
            config.write(f, space_around_delimiters=False)
