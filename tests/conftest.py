import json
from typing import Any, Callable

import pytest

from tests.utils.fixture_helpers import FIXTURES_DIR


@pytest.fixture
def load_json_file() -> Callable:
    """Factory fixture for loading JSON files."""

    def _load_json(filename: str) -> dict[str, Any]:
        filepath = FIXTURES_DIR / filename
        if not filepath.exists():
            raise FileNotFoundError(f"Fixture not found: {filepath}")

        with open(filepath, "r") as f:
            return json.load(f)

    return _load_json


@pytest.fixture
def load_json_string() -> Callable:
    """Factory fixture for loading JSON from a string."""

    def _load_json(json_str: str) -> dict[str, Any]:
        return json.loads(json_str)

    return _load_json
