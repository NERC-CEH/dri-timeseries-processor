import json
from pathlib import Path
from typing import Any

FIXTURES_INPUTS_DIR = Path(__file__).parent.parent / "fixtures" / "inputs"


def discover_json_test_cases(directory: str | Path) -> list[str]:
    """Discover all JSON files in a directory for use with @pytest.mark.parametrize.

    Returns:
        A list of file paths as strings.
    """
    directory = FIXTURES_INPUTS_DIR / Path(directory)
    return [str(p) for p in directory.glob("*.json")]


def load_json_file(filename: str) -> dict[str, Any]:
    """Helper for loading input JSON files."""
    filepath = FIXTURES_INPUTS_DIR / filename
    if not filepath.exists():
        raise FileNotFoundError(f"Fixture not found: {filepath}")

    with open(filepath, "r") as f:
        return json.load(f)


def load_json_string(json_str: str) -> dict[str, Any]:
    """Helper for loading JSON from a string."""
    return json.loads(json_str)
