"""Runner for EddyPro binary processing (eddypro_rp and eddypro_fcc).

eddypro_rp = Raw data Processor
eddypro_fcc = Flux Computation / Corrections

EddyPro binaries (eddypro_rp and eddypro_fcc) are expected to be on PATH in both
local development and production containers.
"""

import logging
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class EddyProResult:
    """Result of an EddyPro processing run."""

    return_code_rp: int
    return_code_fcc: int
    stdout_rp: str
    stderr_rp: str
    stdout_fcc: str
    stderr_fcc: str
    output_dir: Path


class EddyProRunner:
    """Runs the EddyPro binary processing steps (eddypro_rp then eddypro_fcc)"""

    def __init__(self) -> None:
        """Resolve eddypro_rp and eddypro_fcc from PATH.

        Raises:
            FileNotFoundError: If either eddypro_rp or eddypro_fcc cannot be found.
        """
        self._rp_path = self._find_binary("eddypro_rp")
        self._fcc_path = self._find_binary("eddypro_fcc")
        logger.info("EddyPro binaries resolved: rp=%s, fcc=%s", self._rp_path, self._fcc_path)

    def run(
        self,
        project_file: Path,
        output_dir: Path,
        environment: str = "production",
    ) -> EddyProResult:
        """Run both EddyPro processing steps sequentially.

        Step 1: eddypro_rp (raw processor) reads raw 20Hz files and produces
        half-hourly fluxes.
        Step 2: eddypro_fcc (flux correction) applies spectral corrections
        to the eddypro_rp output.

        Args:
            project_file: Path to the .eddypro project file.
            output_dir: Directory where EddyPro writes output.
            environment: Environment string passed to EddyPro.

        Returns:
            EddyProResult with both return codes and captured output.
        """
        work_dir = output_dir.parent
        (work_dir / environment / "tmp").mkdir(parents=True, exist_ok=True)

        base_args = [
            "--system",
            "linux",
            "--mode",
            "desktop",
            "--caller",
            "console",
            "--environment",
            environment,
            str(project_file),
        ]

        # Step 1: eddypro_rp
        logger.info("Running eddypro_rp with project file: %s", project_file)
        rp_result = subprocess.run(
            [self._rp_path, *base_args],
            check=False,
            capture_output=True,
            text=True,
            cwd=work_dir,
        )

        if rp_result.stdout:
            logger.info("eddypro_rp stdout:\n%s", rp_result.stdout)
        if rp_result.stderr:
            logger.warning("eddypro_rp stderr:\n%s", rp_result.stderr)

        if rp_result.returncode != 0:
            logger.error("eddypro_rp failed with return code %d", rp_result.returncode)
            raise RuntimeError(f"eddypro_rp failed with return code {rp_result.returncode}: {rp_result.stderr}")

        logger.info("eddypro_rp completed successfully")

        # Step 2: eddypro_fcc
        logger.info("Running eddypro_fcc with project file: %s", project_file)
        fcc_result = subprocess.run(
            [self._fcc_path, *base_args],
            check=False,
            capture_output=True,
            text=True,
            cwd=work_dir,
        )

        if fcc_result.stdout:
            logger.info("eddypro_fcc stdout:\n%s", fcc_result.stdout)
        if fcc_result.stderr:
            logger.warning("eddypro_fcc stderr:\n%s", fcc_result.stderr)

        if fcc_result.returncode != 0:
            logger.error("eddypro_fcc failed with return code %d", fcc_result.returncode)
            raise RuntimeError(f"eddypro_fcc failed with return code {fcc_result.returncode}: {fcc_result.stderr}")

        logger.info("eddypro_fcc completed successfully")

        return EddyProResult(
            return_code_rp=rp_result.returncode,
            return_code_fcc=fcc_result.returncode,
            stdout_rp=rp_result.stdout,
            stderr_rp=rp_result.stderr,
            stdout_fcc=fcc_result.stdout,
            stderr_fcc=fcc_result.stderr,
            output_dir=output_dir,
        )

    @staticmethod
    def _find_binary(name: str) -> str:
        """Find the path to an EddyPro binary on PATH.

        Args:
            name: Binary name (e.g. "eddypro_rp").

        Returns:
            Full path to the binary.
        """
        found = shutil.which(name)
        if found:
            return found
        raise FileNotFoundError(f"{name} not found in PATH. Ensure EddyPro is installed and on PATH.")
