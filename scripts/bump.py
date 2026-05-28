"""Bump the project version, commit, and create a CHANGELOG stub."""

import re
import subprocess
import sys
import tomllib
from pathlib import Path

PYPROJECT = Path("pyproject.toml")
CITATION = Path("CITATION.cff")


def _read_version() -> str:
    """Read the current project version from pyproject.toml.

    Returns:
        Version string.
    """
    return tomllib.loads(PYPROJECT.read_text())["project"]["version"]


def _update_citation_version(new_version: str) -> bool:
    """Rewrite the top-level ``version:`` line in CITATION.cff if the file exists.

    Args:
        new_version: Version string to write.

    Returns:
        True if the file was found and updated, False otherwise.
    """
    if not CITATION.exists():
        return False
    text = CITATION.read_text()
    new_text, n = re.subn(r"(?m)^version:.*$", f"version: {new_version}", text, count=1)
    if n == 0 or new_text == text:
        return False
    CITATION.write_text(new_text)
    return True


def main() -> None:
    """Bump the version, update CITATION.cff, commit, and optionally create a CHANGELOG stub."""
    raw_args = sys.argv[1:]
    no_changelog = "--no-changelog" in raw_args
    positional = [arg for arg in raw_args if arg != "--no-changelog"]

    if len(positional) != 1 or positional[0] not in ("major", "minor", "patch"):
        print("Usage: bump.py [major|minor|patch] [--no-changelog]")
        sys.exit(1)

    part = positional[0]
    if no_changelog and part != "patch":
        print("Error: --no-changelog is only valid with 'patch'; major/minor bumps require a changelog.")
        sys.exit(1)
    old_version = _read_version()

    subprocess.run(["uv", "version", "--bump", part], check=True)
    new_version = _read_version()

    subprocess.run(["uv", "lock"], check=True)

    to_commit = [str(PYPROJECT), "uv.lock"]
    if _update_citation_version(new_version):
        to_commit.append(str(CITATION))

    subprocess.run(["git", "add", *to_commit], check=True)
    subprocess.run(["git", "commit", "-m", f"Bump version: {old_version} -> {new_version}"], check=True)

    if not no_changelog:
        changelog_path = Path(f"CHANGELOG/{new_version}.md")
        if not changelog_path.exists():
            changelog_path.write_text(f"# {new_version}\n\n<!-- Add release notes here -->\n")
            subprocess.run(["git", "add", str(changelog_path)], check=True)
            subprocess.run(["git", "commit", "-m", f"Add CHANGELOG/{new_version}.md stub"], check=True)

    print()
    print(f"  Bumped to {new_version}.")
    if not no_changelog:
        print(f"  Fill in CHANGELOG/{new_version}.md with your release notes, then commit and push.")
    print()


if __name__ == "__main__":
    main()
