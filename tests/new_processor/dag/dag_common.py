"""Helper functions common to the DAG module"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from utils.fixture_helpers import create_items_list, make_processing_config_container, make_time_series_container


def create_mock_router(items: list) -> MagicMock:
    """Return a mocked MetadataRouter with no-op API calls."""
    mock_router = MagicMock()
    mock_router.fetch_dataset_by_params.return_value = {"items": items}
    mock_router.fetch_all_dependencies.return_value = {"items": items}
    mock_router.fetch_dataset_by_id.return_value = {"items": items}
    mock_router.fetch_processing_configs.return_value = {"items": items}
    return mock_router


def monkeypatch_api_models(monkeypatch: pytest.MonkeyPatch, items: list) -> None:
    """ "Mimic the model_validate of API pydantic models returning a list of dataset dicts"""
    api_models = ["TimeSeriesDatasetResponse", "DataProcessingConfiguration"]
    api_model_return = SimpleNamespace(items=items)
    for api_model in api_models:
        monkeypatch.setattr(f"new_processor.dag.repositories.{api_model}.model_validate", lambda _: api_model_return)


def monkeypatch_mappers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mimic the map_dataset_item Domain->API mapper returning a TimeSeriesContainer and
    Mimic the map_processing_config_item Domain->API mapper returning a ProcessingConfig
    """
    monkeypatch.setattr(
        "new_processor.dag.repositories.map_dataset_item",
        lambda item: make_time_series_container(item["@id"]),
    )

    monkeypatch.setattr(
        "new_processor.dag.repositories.map_processing_config_item",
        lambda item: make_processing_config_container(item["@id"]),
    )


def setup_mocks(ts_ids: str | list[str], monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Mock the pydantic model validators and mapping functions."""
    items = create_items_list(ts_ids)
    mock_router = create_mock_router(items)
    monkeypatch_api_models(monkeypatch, items)
    monkeypatch_mappers(monkeypatch)
    return mock_router
