import subprocess
from pathlib import Path
from unittest.mock import MagicMock, call

import pytest

from dritimeseriesprocessor.operations.eddypro.eddypro_runner import EddyProRunner


class TestEddyProRunner:
    def test_init_resolves_binaries_from_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
        which = MagicMock(side_effect=["/opt/eddypro/bin/eddypro_rp", "/opt/eddypro/bin/eddypro_fcc"])
        monkeypatch.setattr("dritimeseriesprocessor.operations.eddypro.eddypro_runner.shutil.which", which)

        runner = EddyProRunner()

        assert runner._rp_path == "/opt/eddypro/bin/eddypro_rp"
        assert runner._fcc_path == "/opt/eddypro/bin/eddypro_fcc"

    def test_find_binary_raises_when_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("dritimeseriesprocessor.operations.eddypro.eddypro_runner.shutil.which", lambda _: None)

        with pytest.raises(FileNotFoundError, match="eddypro_rp not found in PATH"):
            EddyProRunner._find_binary("eddypro_rp")

    def test_run_executes_rp_then_fcc(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        runner = object.__new__(EddyProRunner)
        runner._rp_path = "/opt/eddypro/bin/eddypro_rp"
        runner._fcc_path = "/opt/eddypro/bin/eddypro_fcc"

        subprocess_run = MagicMock(
            side_effect=[
                subprocess.CompletedProcess(args=[], returncode=0, stdout="rp ok", stderr=""),
                subprocess.CompletedProcess(args=[], returncode=0, stdout="fcc ok", stderr=""),
            ]
        )
        monkeypatch.setattr("dritimeseriesprocessor.operations.eddypro.eddypro_runner.subprocess.run", subprocess_run)

        project_file = tmp_path / "config" / "processing.eddypro"
        project_file.parent.mkdir(parents=True)
        project_file.write_text("project")
        output_dir = tmp_path / "output"

        result = runner.run(project_file=project_file, output_dir=output_dir, environment="testing")

        expected_args = [
            "--system",
            "linux",
            "--mode",
            "desktop",
            "--caller",
            "console",
            "--environment",
            "testing",
            str(project_file),
        ]
        assert subprocess_run.call_args_list == [
            call(
                ["/opt/eddypro/bin/eddypro_rp", *expected_args],
                check=False,
                capture_output=True,
                text=True,
                cwd=tmp_path,
            ),
            call(
                ["/opt/eddypro/bin/eddypro_fcc", *expected_args],
                check=False,
                capture_output=True,
                text=True,
                cwd=tmp_path,
            ),
        ]
        assert result.return_code_rp == 0
        assert result.return_code_fcc == 0
        assert result.output_dir == output_dir
        assert (tmp_path / "testing" / "tmp").exists()

    def test_run_raises_when_rp_fails(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        runner = object.__new__(EddyProRunner)
        runner._rp_path = "/opt/eddypro/bin/eddypro_rp"
        runner._fcc_path = "/opt/eddypro/bin/eddypro_fcc"

        subprocess_run = MagicMock(
            return_value=subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="STOP 1")
        )
        monkeypatch.setattr("dritimeseriesprocessor.operations.eddypro.eddypro_runner.subprocess.run", subprocess_run)

        with pytest.raises(RuntimeError, match="eddypro_rp failed with return code 1"):
            runner.run(project_file=tmp_path / "processing.eddypro", output_dir=tmp_path / "output")

        subprocess_run.assert_called_once()

    def test_run_raises_when_fcc_fails(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        runner = object.__new__(EddyProRunner)
        runner._rp_path = "/opt/eddypro/bin/eddypro_rp"
        runner._fcc_path = "/opt/eddypro/bin/eddypro_fcc"

        subprocess_run = MagicMock(
            side_effect=[
                subprocess.CompletedProcess(args=[], returncode=0, stdout="rp ok", stderr=""),
                subprocess.CompletedProcess(args=[], returncode=2, stdout="", stderr="fcc failed"),
            ]
        )
        monkeypatch.setattr("dritimeseriesprocessor.operations.eddypro.eddypro_runner.subprocess.run", subprocess_run)

        with pytest.raises(RuntimeError, match="eddypro_fcc failed with return code 2"):
            runner.run(project_file=tmp_path / "processing.eddypro", output_dir=tmp_path / "output")

        assert subprocess_run.call_count == 2
