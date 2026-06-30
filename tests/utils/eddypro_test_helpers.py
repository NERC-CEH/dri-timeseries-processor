from pathlib import Path

from dritimeseriesprocessor.operations.eddypro.eddypro_runner import EddyProResult, EddyProRunner

EDDYPRO_OUTPUT_DIR = Path(__file__).parent.parent / "data" / "inputs" / "eddypro_output"


def eddypro_mock_init(self: EddyProRunner) -> None:
    pass


def eddypro_mock_run(
    self: EddyProRunner, project_file: Path, output_dir: Path, environment: str = "production"
) -> EddyProResult:
    return EddyProResult(
        return_code_rp=0,
        return_code_fcc=0,
        stdout_rp="",
        stderr_rp="",
        stdout_fcc="",
        stderr_fcc="",
        output_dir=EDDYPRO_OUTPUT_DIR,
    )
