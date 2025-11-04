import json
from pathlib import Path
from typing import Any

import pytest
from _pytest.mark.structures import ParameterSet

FIXTURES_INPUTS_DIR = Path(__file__).parent.parent / "fixtures" / "inputs"


def discover_json_test_cases(directory: str | Path) -> list[ParameterSet]:
    """Discover all JSON files in a directory for use with @pytest.mark.parametrize.

    Returns:
        A list of pytest.param objects, each representing a JSON file.
    """
    directory = FIXTURES_INPUTS_DIR / Path(directory)

    test_cases = []
    for path in directory.glob("*.json"):
        # Create a readable relative ID for test display
        relative_path_id = str(path.relative_to(FIXTURES_INPUTS_DIR))
        test_cases.append(pytest.param(str(path), id=relative_path_id))

    return test_cases


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
