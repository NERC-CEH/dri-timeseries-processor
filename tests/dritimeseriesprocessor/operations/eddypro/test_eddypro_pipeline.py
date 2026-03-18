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
    ) -> Path:
        FakeConfigBuilder.project_call = {
            "template_path": template_path,
            "working_dir": working_dir,
            "raw_data_dir": raw_data_dir,
            "output_dir": output_dir,
            "start_date": start_date,
            "end_date": end_date,
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
            site="PLYNL",
            processed_dataset="eddypro-full-output",
            start_date=date(2026, 1, 20),
        )
        assert "path" in captured_work_dir
        assert not captured_work_dir["path"].exists()

    def test_run_requires_site_alt_id(self) -> None:
        pipeline = EddyProPipeline(runner=MagicMock(), config_builder_cls=FakeConfigBuilder)

        with pytest.raises(ValueError, match="Site metadata missing alt_id"):
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
                flux_s3_client=MagicMock(),
                network="fdri",
                processed_source_bucket="processed-bucket",
                processed_dataset="eddypro-full-output",
            )
