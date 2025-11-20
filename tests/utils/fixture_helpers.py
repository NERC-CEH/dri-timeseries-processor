import json
from pathlib import Path
from typing import Any

import pytest
from _pytest.mark.structures import ParameterSet

from new_processor.domain_models.processing_config import ProcessingConfig
from new_processor.domain_models.time_series_container import TimeSeriesContainer
from new_processor.utils.enums import ConfigurationType, ProcessingLevel

TEST_DATA_INPUT_DIR = Path(__file__).parent.parent / "data" / "inputs"
TEST_DATA_API_VALID = TEST_DATA_INPUT_DIR / "api_json" / "valid"
TEST_DATA_API_INVALID = TEST_DATA_INPUT_DIR / "api_json" / "invalid"


def discover_json_test_cases(directory: str | Path) -> list[ParameterSet]:
    """Discover all JSON files in a directory for use with @pytest.mark.parametrize.

    Returns:
        A list of pytest.param objects, each representing a JSON file.
    """
    directory = TEST_DATA_INPUT_DIR / Path(directory)

    test_cases = []
    for path in directory.glob("*.json"):
        # Create a readable relative ID for test display
        relative_path_id = str(path.relative_to(TEST_DATA_INPUT_DIR))
        test_cases.append(pytest.param(str(path), id=relative_path_id))

    return test_cases


def load_json_file(filename: str) -> dict[str, Any]:
    """Helper for loading input JSON files."""
    filepath = TEST_DATA_INPUT_DIR / filename
    if not filepath.exists():
        raise FileNotFoundError(f"Fixture not found: {filepath}")

    with open(filepath, "r") as f:
        return json.load(f)


def load_json_string(json_str: str) -> dict[str, Any]:
    """Helper for loading JSON from a string."""
    return json.loads(json_str)


def make_time_series_container(
    ts_id: str,
    depends_on: list[str] | None = None,
    processing_level: ProcessingLevel | None = ProcessingLevel.PROCESSED,
) -> TimeSeriesContainer:
    """Create a lightweight fake TimeSeriesContainer for use in tests.

    Args:
        ts_id: The time series ID.
        depends_on: Optional list of dataset IDs that this container depends on.
        processing_level: Optional processing level.
    Returns:
        A TimeSeriesContainer instance
    """
    return TimeSeriesContainer(
        ts_id=ts_id,
        ref_id=ts_id + "_ref",
        source_bucket=ts_id + "_bucket",
        source_site=ts_id + "_site",
        source_column=ts_id + "_column",
        source_dataset=ts_id + "_dataset",
        resolution=ts_id + "_resolution",
        periodicity=ts_id + "_periodicity",
        variable=ts_id + "_variable",
        processing_level=processing_level,
        depends_on=depends_on or [],
        qc_configs=set(),
        infill_configs=set(),
        correction_configs=set(),
    )


def make_processing_config_container(
    ts_id: str, config_type: ConfigurationType | None = ConfigurationType.CORRECTION
) -> ProcessingConfig:
    """Create a lightweight fake ProcessingConfig for a given dataset.

    Args:
        ts_id: The time series ID that the configuration applies to.
        config_type: Optional configuration type.

    Returns:
        A ProcessingConfig instance
    """
    return ProcessingConfig(
        ts_id=ts_id,
        config_id=ts_id + "_config_id",
        config_type=config_type,
        method_configs=[],
        annotations={},
    )


def create_items_list(ts_ids: str | list) -> list:
    """Create a simple list of items in a format mocking response from metadata API"""
    if isinstance(ts_ids, str):
        ts_ids = [ts_ids]
    items = [{"@id": ts_id} for ts_id in ts_ids]
    return items
