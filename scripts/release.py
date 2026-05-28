"""Tag the current version and create a GitHub release."""

import subprocess
import sys
import tomllib
from pathlib import Path


def _run(*cmd: str) -> None:
    """Print and execute a command, raising on non-zero exit."""
    print(f"$ {' '.join(cmd)}")  # noqa: T201
    subprocess.run(cmd, check=True)


def _current_branch() -> str:
    """Return the name of the currently checked-out git branch."""
    return subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def main() -> None:
    """Tag the current version and create a GitHub release from production."""
    branch = _current_branch()
    if branch != "production":
        print(f"Error: `make release` must be run from production, not '{branch}'.")  # noqa: T201
        sys.exit(1)

    pyproject = tomllib.loads(Path("pyproject.toml").read_text())
    name = pyproject["project"]["name"]
    version = pyproject["project"]["version"]
    tag = f"v{version}"
    notes_path = Path(f"CHANGELOG/{version}.md")

    lines = notes_path.read_text().splitlines(keepends=True)
    title = f"{name} {version}"
    if lines and lines[0].startswith("# "):
        title = lines[0].lstrip("# ").strip()
        lines = lines[1:]
        if lines and not lines[0].strip():
            lines = lines[1:]
    notes = "".join(lines).rstrip()

    _run("git", "tag", "-a", tag, "-m", f"Release {tag}")
    _run("git", "push", "origin", tag)
    _run("gh", "release", "create", tag, "--verify-tag", "--title", title, "--notes", notes)


if __name__ == "__main__":
    main()
