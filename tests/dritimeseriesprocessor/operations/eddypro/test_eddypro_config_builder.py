from configparser import ConfigParser
from datetime import date
from pathlib import Path

from dritimeseriesprocessor import PACKAGE_ROOT
from dritimeseriesprocessor.operations.eddypro.eddypro_config_builder import EddyProConfigBuilder
from dritimeseriesprocessor.operations.eddypro.eddypro_run_spec import (
    EddyProColumnSpec,
    EddyProInstrumentSpec,
    EddyProRunSpec,
)


def read_ini(path: Path) -> ConfigParser:
    config = ConfigParser()
    config.optionxform = str  # type: ignore[assignment]
    text = path.read_text()
    lines = text.splitlines(keepends=True)
    if lines and lines[0].startswith(";"):
        text = "".join(lines[1:])
    config.read_string(text)
    return config


class TestEddyProConfigBuilder:
    def test_build_project_file_populates_template(self, tmp_path: Path) -> None:
        builder = EddyProConfigBuilder(
            run_spec=EddyProRunSpec(
                site_code="PLYNL",
                software_version="7.0.9",
                file_prototype="TOA5_*.dat",
                master_sonic="csat3_1",
                columns=[
                    EddyProColumnSpec(variable="u"),
                    EddyProColumnSpec(variable="anemometer_diagnostic"),
                    EddyProColumnSpec(variable="co2"),
                    EddyProColumnSpec(variable="h2o"),
                    EddyProColumnSpec(variable="air_t"),
                    EddyProColumnSpec(variable="cell_t"),
                    EddyProColumnSpec(variable="int_p"),
                    EddyProColumnSpec(variable="air_p"),
                ],
            )
        )

        project_path = builder.build_project_file(
            template_path=PACKAGE_ROOT / "__assets__" / "eddypro_templates" / "processing_template.eddypro",
            working_dir=tmp_path / "config",
            raw_data_dir=tmp_path / "raw",
            output_dir=tmp_path / "output",
            start_date=date(2026, 1, 20),
            end_date=date(2026, 1, 21),
        )

        config = read_ini(project_path)
        assert project_path.name == "processing.eddypro"
        assert config.get("Project", "project_id") == "PLYNL"
        assert config.get("Project", "file_prototype") == "TOA5_*.dat"
        assert config.get("Project", "master_sonic") == "csat3_1"
        assert config.get("Project", "pr_start_date") == "2026-01-20"
        assert config.get("Project", "pr_end_date") == "2026-01-21"
        assert config.get("Project", "sw_version") == "7.0.9"
        assert config.get("Project", "proj_file").endswith("PLYNL.metadata")
        assert config.get("Project", "use_dyn_md_file") == "0"
        assert config.get("Project", "dyn_metadata_file") == ""
        assert config.get("Project", "use_biom") == "0"
        assert config.get("Project", "biom_file") == ""
        assert config.get("Project", "biom_dir") == ""
        assert config.get("RawProcess_General", "data_path") == str(tmp_path / "raw")
        assert config.get("Project", "col_diag_anem") == "2"
        assert config.get("Project", "col_co2") == "3"
        assert config.get("Project", "col_h2o") == "4"
        assert config.get("Project", "col_air_t") == "5"
        assert config.get("Project", "col_cell_t") == "6"
        assert config.get("Project", "col_int_p") == "7"
        assert config.get("Project", "col_air_p") == "8"

    def test_build_project_file_populates_ancillary_file_settings(self, tmp_path: Path) -> None:
        builder = EddyProConfigBuilder(
            run_spec=EddyProRunSpec(
                site_code="PLYNL",
                software_version="7.0.9",
                file_prototype="TOA5_*.dat",
                columns=[EddyProColumnSpec(variable="u")],
            )
        )

        biomet_file = tmp_path / "inputs" / "biomet.csv"
        dynamic_metadata_file = tmp_path / "inputs" / "dynamic_metadata.txt"

        project_path = builder.build_project_file(
            template_path=PACKAGE_ROOT / "__assets__" / "eddypro_templates" / "processing_template.eddypro",
            working_dir=tmp_path / "config",
            raw_data_dir=tmp_path / "raw",
            output_dir=tmp_path / "output",
            start_date=date(2026, 1, 20),
            end_date=date(2026, 1, 21),
            biomet_file=biomet_file,
            dynamic_metadata_file=dynamic_metadata_file,
        )

        config = read_ini(project_path)
        assert config.get("Project", "use_dyn_md_file") == "1"
        assert config.get("Project", "dyn_metadata_file") == str(dynamic_metadata_file)
        assert config.get("Project", "use_biom") == "2"
        assert config.get("Project", "biom_file") == str(biomet_file)
        assert config.get("Project", "biom_dir") == str(biomet_file.parent)

    def test_build_metadata_file_populates_site_instrument_and_columns(self, tmp_path: Path) -> None:
        builder = EddyProConfigBuilder(
            run_spec=EddyProRunSpec(
                site_code="PLYNL",
                software_version="7.0.9",
                acquisition_frequency=20.0,
                file_duration=30,
                canopy_height=0.2,
                displacement_height=0.13,
                roughness_length=0.01,
                latitude=52.45,
                longitude=-3.75,
                altitude=540.0,
                instruments=[
                    EddyProInstrumentSpec(fields={"manufacturer": "csi", "model": "csat3_1"}),
                    EddyProInstrumentSpec(fields={"manufacturer": "licor", "model": "li-7200"}),
                ],
                columns=[
                    EddyProColumnSpec(variable="u", instrument="csat3_1", unit_in="m_sec"),
                    EddyProColumnSpec(variable="co2", instrument="li7200", unit_in="ppm"),
                ],
            )
        )

        metadata_path = builder.build_metadata_file(
            template_path=PACKAGE_ROOT / "__assets__" / "eddypro_templates" / "metadata_template.metadata",
            working_dir=tmp_path / "config",
            start_date=date(2026, 1, 20),
            end_date=date(2026, 1, 21),
        )

        config = read_ini(metadata_path)
        assert metadata_path.name == "PLYNL.metadata"
        assert config.get("Project", "id") == "PLYNL"
        assert config.get("Project", "sw_version") == "7.0.9"
        assert config.get("Project", "start_date") == "2026-01-20"
        assert config.get("Project", "end_date") == "2026-01-21"
        assert config.get("Site", "site_name") == "PLYNL"
        assert config.get("Site", "altitude") == "540.0"
        assert config.get("Site", "latitude") == "52.45"
        assert config.get("Site", "longitude") == "-3.75"
        assert config.get("Site", "canopy_height") == "0.2"
        assert config.get("Site", "displacement_height") == "0.13"
        assert config.get("Site", "roughness_length") == "0.01"
        assert config.get("Timing", "acquisition_frequency") == "20.0"
        assert config.get("Timing", "file_duration") == "30"
        assert config.get("Instruments", "instr_1_manufacturer") == "csi"
        assert config.get("Instruments", "instr_2_model") == "li-7200"
        assert config.get("FileDescription", "separator") == "comma"
        assert config.get("FileDescription", "col_1_variable") == "u"
        assert config.get("FileDescription", "col_2_instrument") == "li7200"
