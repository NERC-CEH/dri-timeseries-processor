from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from dritimeseriesprocessor.models.domain_models.processing_config import DataProcessingConfig
from dritimeseriesprocessor.models.domain_models.site_metadata import SiteMetadata
from dritimeseriesprocessor.operations.eddypro.eddypro_pipeline import EddyProPipeline
from dritimeseriesprocessor.operations.eddypro.eddypro_run_spec import EddyProRunSpec
from dritimeseriesprocessor.operations.eddypro.eddypro_runner import EddyProResult
from dritimeseriesprocessor.utils.enums import ConfigurationType


class FakeConfigBuilder:
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


class TestEddyProPipeline:
    def setup_method(self) -> None:
        FakeConfigBuilder.latest_run_spec = None
        FakeConfigBuilder.project_call = None
        FakeConfigBuilder.metadata_call = None

    def test_run_builds_configs_runs_eddypro_and_uploads_outputs(
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
            (output_dir / "eddypro_full_output.csv").write_text("output")
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
        flux_s3_client = MagicMock()

        pipeline = EddyProPipeline(runner=runner, config_builder_cls=FakeConfigBuilder)
        pipeline.run(
            raw_data_dir=staged_raw_dir,
            method_config=DataProcessingConfig(
                ts_id="http://fdri.ceh.ac.uk/id/dataset/flux-plynl-eddypro-full-output",
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
            flux_s3_client=flux_s3_client,
            network="fdri",
            processed_source_bucket="processed-bucket",
            processed_dataset="eddypro-full-output",
        )

        assert FakeConfigBuilder.latest_run_spec == EddyProRunSpec(site_code="PLYNL")
        assert FakeConfigBuilder.project_call is not None
        assert FakeConfigBuilder.project_call["raw_data_dir"] == staged_raw_dir
        assert FakeConfigBuilder.metadata_call is not None
        runner.run.assert_called_once()
        flux_s3_client.upload_output_files.assert_called_once_with(
            bucket="processed-bucket",
            output_dir=FakeConfigBuilder.project_call["output_dir"],
            network="fdri",
            site="flux-plynl",
            processed_dataset="eddypro-full-output",
            start_date=date(2026, 1, 20),
        )
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
        runner.run.return_value = EddyProResult(
            return_code_rp=0,
            return_code_fcc=0,
            stdout_rp="rp ok",
            stderr_rp="",
            stdout_fcc="fcc ok",
            stderr_fcc="",
            output_dir=tmp_path / "output",
        )
        flux_s3_client = MagicMock()

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
            ancillary_containers=ancillary_containers,
            flux_s3_client=flux_s3_client,
            network="fdri",
            processed_source_bucket="processed-bucket",
            processed_dataset="eddypro-full-output",
        )

        assert FakeConfigBuilder.project_call is not None
        assert FakeConfigBuilder.project_call["biomet_file"] == biomet_path
        assert FakeConfigBuilder.project_call["dynamic_metadata_file"] == dynamic_metadata_path

    def test_run_falls_back_to_site_id_when_alt_id_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
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

        pipeline = EddyProPipeline(runner=MagicMock(), config_builder_cls=FakeConfigBuilder)
        flux_s3_client = MagicMock()

        pipeline.run(
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
            flux_s3_client=flux_s3_client,
            network="fdri",
            processed_source_bucket="processed-bucket",
            processed_dataset="eddypro-full-output",
        )

        flux_s3_client.upload_output_files.assert_called_once()
        assert flux_s3_client.upload_output_files.call_args.kwargs["site"] == "flux-plynl"
