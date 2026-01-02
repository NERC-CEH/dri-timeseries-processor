import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from new_processor.models.api_models.flags import CoreFlagResponse
from new_processor.routers.metadata.local_loader import fetch_core_flags, load_metadata_json


def monkeypatch_package_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("new_processor.routers.metadata.local_loader.PACKAGE_ROOT", tmp_path)


def monkeypatch_load_metadata_json(monkeypatch: pytest.MonkeyPatch, test_data: dict) -> MagicMock:
    mock_load = MagicMock()
    mock_load.return_value = test_data
    monkeypatch.setattr("new_processor.routers.metadata.local_loader.load_metadata_json", mock_load)
    return mock_load


def setup_test_data(tmp_path: Path, test_data: dict | str | None = None, file_name: str | None = None) -> None:
    metadata_dir = tmp_path / "__metadata__"
    metadata_dir.mkdir(parents=True)

    if not file_name:
        file_name = "test.json"

    if test_data is not None:
        test_file = metadata_dir / file_name
        if isinstance(test_data, dict):
            test_data = json.dumps(test_data)
        test_file.write_text(test_data)


class TestLoadMetadataJson:
    def test_loads_valid_json_file(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test loading a valid JSON file."""
        test_data = {"key": "value", "number": 123}
        monkeypatch_package_root(tmp_path, monkeypatch)
        setup_test_data(tmp_path, test_data)
        result = load_metadata_json("test.json")
        assert result == test_data

    def test_invalid_json(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that invalid JSON raises JSONDecodeError."""
        test_data = "invalid json {"
        monkeypatch_package_root(tmp_path, monkeypatch)
        setup_test_data(tmp_path, test_data)
        with pytest.raises(json.JSONDecodeError):
            load_metadata_json("test.json")

    def test_file_not_found(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that missing file raises FileNotFoundError."""
        monkeypatch_package_root(tmp_path, monkeypatch)
        with pytest.raises(FileNotFoundError):
            load_metadata_json("missing.json")


class TestFetchCoreFlags:
    def setup_method(self) -> None:
        """Clear the LRU cache before each test."""
        fetch_core_flags.cache_clear()

    def teardown_method(self):
        """Clear the LRU cache after each test so as not to leak into downstream tests."""
        fetch_core_flags.cache_clear()

    def test_valid_core_flag_response(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        test_data = {
            "core_flags": {
                "missing": {"name": "missing", "description": "Data is missing", "symbol": "M", "id": 1},
                "estimated": {"name": "estimated", "description": "Data is estimated", "symbol": "E", "id": 2},
            }
        }
        monkeypatch_load_metadata_json(monkeypatch, test_data)
        result = fetch_core_flags()
        assert isinstance(result, CoreFlagResponse)

    def test_caches_result(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that fetch_core_flags caches the result using lru_cache."""
        test_data = {
            "core_flags": {"missing": {"name": "missing", "description": "Data is missing", "symbol": "M", "id": 1}}
        }
        mock_load = monkeypatch_load_metadata_json(monkeypatch, test_data)

        fetch_core_flags()
        fetch_core_flags()
        fetch_core_flags()

        # load_metadata_json should only be called once due to caching
        mock_load.assert_called_once()
