from datetime import date, datetime
from pathlib import Path
from typing import cast
from unittest.mock import MagicMock

import polars as pl
import pytest

from dritimeseriesprocessor.models.domain_models.processing_config import DataProcessingConfig
from dritimeseriesprocessor.models.domain_models.site_metadata import SiteMetadata
from dritimeseriesprocessor.models.domain_models.time_series_container import TimeSeriesContainer
from dritimeseriesprocessor.operations.eddypro.eddypro_config_builder import EddyProConfigBuilder
from dritimeseriesprocessor.operations.eddypro.eddypro_pipeline import EddyProPipeline, _parse_eddypro_output
from dritimeseriesprocessor.operations.eddypro.eddypro_run_spec import EddyProRunSpec
from dritimeseriesprocessor.operations.eddypro.eddypro_runner import EddyProResult
from dritimeseriesprocessor.utils.enums import ConfigurationType

_FULL_OUTPUT_HEADER = "file,date,time,DoY,H,qc_H,Tau,qc_Tau,co2_flux\n"
_FULL_OUTPUT_UNITS = "---,yyyy-mm-dd,HH:MM,---,W/m^2,#,N/m^2,#,umol/(m^2 s)\n"
_FULL_OUTPUT_DATA = "file1.dat,2024-01-20,00:30,20,150.0,0,0.5,0,5.0\n"


def _write_full_output(output_dir: Path) -> None:
    """Write a minimal full_output CSV to output_dir."""
    f = output_dir / "EP_full_output.csv"
    f.write_text("EddyPro run info\n" + _FULL_OUTPUT_HEADER + _FULL_OUTPUT_UNITS + _FULL_OUTPUT_DATA)


class FakeConfigBuilder(EddyProConfigBuilder):
    latest_run_spec: EddyProRunSpec | None = None
    project_call: dict | None = None
    metadata_call: dict | None = None

    def __init__(self, run_spec: EddyProRunSpec) -> None:
        FakeConfigBuilder.latest_run_spec = run_spec

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
        FakeConfigBuilder.project_call = {
            "template_path": template_path,
            "working_dir": working_dir,
            "raw_data_dir": raw_data_dir,
            "output_dir": output_dir,
            "start_date": start_date,
            "end_date": end_date,
            "biomet_file": biomet_file,
            "dynamic_metadata_file": dynamic_metadata_file,
        }
        output = working_dir / "processing.eddypro"
        output.write_text("project")
        return output

    def build_metadata_file(
        self,
        template_path: Path,
        working_dir: Path,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> Path:
        FakeConfigBuilder.metadata_call = {
            "template_path": template_path,
            "working_dir": working_dir,
            "start_date": start_date,
            "end_date": end_date,
        }
        output = working_dir / "PLYNL.metadata"
        output.write_text("metadata")
        return output


class TestParseEddyProOutput:
    def test_time_column_shifted_back_30_minutes(self, tmp_path: Path) -> None:
        """full_output timestamps are end-of-period; parser shifts them to start-of-period."""
        (tmp_path / "EP_full_output.csv").write_text(
            "EddyPro run info\nfile,date,time,H\n---,yyyy-mm-dd,HH:MM,W/m^2\nfile1.dat,2024-01-20,14:30,150.0\n"
        )

        result = _parse_eddypro_output(tmp_path)

        assert "time" in result.columns
        assert "DateTime" not in result.columns
        assert result["time"][0] == datetime(2024, 1, 20, 14, 0)

    def test_minus9999_converted_to_null(self, tmp_path: Path) -> None:
        (tmp_path / "EP_full_output.csv").write_text(
            "EddyPro run info\nfile,date,time,H\n---,yyyy-mm-dd,HH:MM,W/m^2\nfile1.dat,2024-01-20,00:30,-9999\n"
        )

        result = _parse_eddypro_output(tmp_path)

        assert result["H"][0] is None

    def test_qc_details_columns_merged(self, tmp_path: Path) -> None:
        (tmp_path / "EP_full_output.csv").write_text(
            "EddyPro run info\nfile,date,time,H\n---,yyyy-mm-dd,HH:MM,W/m^2\nfile1.dat,2024-01-20,00:30,150.0\n"
        )
        (tmp_path / "EP_qc_details.csv").write_text(
            "EddyPro run info\nfile,date,time,qc_H\n---,yyyy-mm-dd,HH:MM,#\nfile1.dat,2024-01-20,00:30,0\n"
        )

        result = _parse_eddypro_output(tmp_path)

        assert "qc_H" in result.columns

    def test_biomet_columns_merged(self, tmp_path: Path) -> None:
        (tmp_path / "EP_full_output.csv").write_text(
            "EddyPro run info\nfile,date,time,H\n---,yyyy-mm-dd,HH:MM,W/m^2\nfile1.dat,2024-01-20,00:30,150.0\n"
        )
        (tmp_path / "EP_biomet.csv").write_text("date,time,Ta\nyyyy-mm-dd,HH:MM,degC\n2024-01-20,00:30,12.5\n")

        result = _parse_eddypro_output(tmp_path)

        assert "Ta" in result.columns

    def test_raises_when_no_full_output(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            _parse_eddypro_output(tmp_path)


class TestEddyProPipeline:
    def setup_method(self) -> None:
        FakeConfigBuilder.latest_run_spec = None
        FakeConfigBuilder.project_call = None
        FakeConfigBuilder.metadata_call = None

    def test_run_builds_configs_runs_eddypro_and_returns_dataframe(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def fake_build_run_spec(
            self: object,
            config: DataProcessingConfig,
            site_metadata: SiteMetadata,
        ) -> EddyProRunSpec:
            return EddyProRunSpec(site_code="PLYNL")

        monkeypatch.setattr(
            "dritimeseriesprocessor.operations.eddypro.eddypro_pipeline.EddyProMetadataMapper.build_run_spec",
            fake_build_run_spec,
        )
        monkeypatch.setattr(
            "dritimeseriesprocessor.operations.eddypro.eddypro_pipeline.EddyProBiometBuilder.build",
            MagicMock(return_value=None),
        )
        monkeypatch.setattr(
            "dritimeseriesprocessor.operations.eddypro.eddypro_pipeline.EddyProDynamicMetadataBuilder.build",
            MagicMock(return_value=None),
        )

        staged_raw_dir = tmp_path / "raw"
        staged_raw_dir.mkdir()
        captured_work_dir: dict[str, Path] = {}

        runner = MagicMock()

        def fake_run(project_file: Path, output_dir: Path) -> EddyProResult:
            captured_work_dir["path"] = output_dir.parent
            _write_full_output(output_dir)
            return EddyProResult(
                return_code_rp=0,
                return_code_fcc=0,
                stdout_rp="rp ok",
                stderr_rp="",
                stdout_fcc="fcc ok",
                stderr_fcc="",
                output_dir=output_dir,
            )

        runner.run.side_effect = fake_run

        pipeline = EddyProPipeline(runner=runner, config_builder_cls=FakeConfigBuilder)
        result = pipeline.run(
            raw_data_dir=staged_raw_dir,
            method_config=DataProcessingConfig(
                ts_id="http://fdri.ceh.ac.uk/id/dataset/flux-plynl-processed",
                config_id="config-1",
                config_type=ConfigurationType.EDDYPRO,
                method_configs=[],
            ),
            site_metadata=SiteMetadata(
                site_id="http://fdri.ceh.ac.uk/id/site/flux-plynl",
                network="fdri",
                alt_id="PLYNL",
            ),
            start_date=date(2026, 1, 20),
            end_date=date(2026, 1, 21),
            ancillary_containers=None,
        )

        assert FakeConfigBuilder.latest_run_spec == EddyProRunSpec(site_code="PLYNL")
        assert FakeConfigBuilder.project_call is not None
        assert FakeConfigBuilder.project_call["raw_data_dir"] == staged_raw_dir
        assert FakeConfigBuilder.metadata_call is not None
        runner.run.assert_called_once()
        # Returns a Polars DataFrame with flux columns
        assert isinstance(result, pl.DataFrame)
        assert "H" in result.columns
        assert "time" in result.columns
        assert "path" in captured_work_dir
        assert not captured_work_dir["path"].exists()

    def test_run_passes_ancillary_builder_outputs_to_config_builder(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ancillary_containers = [MagicMock()]
        biomet_path = tmp_path / "inputs" / "biomet.csv"
        dynamic_metadata_path = tmp_path / "inputs" / "dynamic_metadata.txt"

        def fake_build_run_spec(
            self: object,
            config: DataProcessingConfig,
            site_metadata: SiteMetadata,
        ) -> EddyProRunSpec:
            return EddyProRunSpec(site_code="PLYNL")

        monkeypatch.setattr(
            "dritimeseriesprocessor.operations.eddypro.eddypro_pipeline.EddyProMetadataMapper.build_run_spec",
            fake_build_run_spec,
        )
        monkeypatch.setattr(
            "dritimeseriesprocessor.operations.eddypro.eddypro_pipeline.EddyProBiometBuilder.build",
            lambda self, containers, output_path: biomet_path,
        )
        monkeypatch.setattr(
            "dritimeseriesprocessor.operations.eddypro.eddypro_pipeline.EddyProDynamicMetadataBuilder.build",
            lambda self, containers, output_path: dynamic_metadata_path,
        )

        runner = MagicMock()

        def fake_run(project_file: Path, output_dir: Path) -> EddyProResult:
            _write_full_output(output_dir)
            return EddyProResult(
                return_code_rp=0,
                return_code_fcc=0,
                stdout_rp="rp ok",
                stderr_rp="",
                stdout_fcc="fcc ok",
                stderr_fcc="",
                output_dir=output_dir,
            )

        runner.run.side_effect = fake_run

        pipeline = EddyProPipeline(runner=runner, config_builder_cls=FakeConfigBuilder)
        pipeline.run(
            raw_data_dir=tmp_path / "raw",
            method_config=DataProcessingConfig(
                ts_id="dataset",
                config_id="config-1",
                config_type=ConfigurationType.EDDYPRO,
                method_configs=[],
            ),
            site_metadata=SiteMetadata(
                site_id="http://fdri.ceh.ac.uk/id/site/flux-plynl",
                network="fdri",
                alt_id="PLYNL",
            ),
            start_date=date(2026, 1, 20),
            end_date=date(2026, 1, 21),
            ancillary_containers=cast(list[TimeSeriesContainer], ancillary_containers),
        )

        assert FakeConfigBuilder.project_call is not None
        assert FakeConfigBuilder.project_call["biomet_file"] == biomet_path
        assert FakeConfigBuilder.project_call["dynamic_metadata_file"] == dynamic_metadata_path

    def test_run_falls_back_to_site_id_when_alt_id_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def fake_build_run_spec(
            self: object,
            config: DataProcessingConfig,
            site_metadata: SiteMetadata,
        ) -> EddyProRunSpec:
            return EddyProRunSpec(site_code="")

        monkeypatch.setattr(
            "dritimeseriesprocessor.operations.eddypro.eddypro_pipeline.EddyProMetadataMapper.build_run_spec",
            fake_build_run_spec,
        )
        monkeypatch.setattr(
            "dritimeseriesprocessor.operations.eddypro.eddypro_pipeline.EddyProBiometBuilder.build",
            MagicMock(return_value=None),
        )
        monkeypatch.setattr(
            "dritimeseriesprocessor.operations.eddypro.eddypro_pipeline.EddyProDynamicMetadataBuilder.build",
            MagicMock(return_value=None),
        )

        runner = MagicMock()

        def fake_run(project_file: Path, output_dir: Path) -> EddyProResult:
            _write_full_output(output_dir)
            return EddyProResult(
                return_code_rp=0,
                return_code_fcc=0,
                stdout_rp="rp ok",
                stderr_rp="",
                stdout_fcc="fcc ok",
                stderr_fcc="",
                output_dir=output_dir,
            )

        runner.run.side_effect = fake_run

        pipeline = EddyProPipeline(runner=runner, config_builder_cls=FakeConfigBuilder)
        result = pipeline.run(
            raw_data_dir=Path("/tmp/raw"),
            method_config=DataProcessingConfig(
                ts_id="dataset",
                config_id="config-1",
                config_type=ConfigurationType.EDDYPRO,
                method_configs=[],
            ),
            site_metadata=SiteMetadata(
                site_id="http://fdri.ceh.ac.uk/id/site/flux-plynl",
                network="fdri",
                alt_id=None,
            ),
            start_date=date(2026, 1, 20),
            end_date=date(2026, 1, 21),
            ancillary_containers=None,
        )

        assert isinstance(result, pl.DataFrame)
