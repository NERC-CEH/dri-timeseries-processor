import pytest
from dag_common import setup_mocks

from new_processor.dag.repositories import ConfigRepository, DatasetRepository
from utils.fixture_helpers import make_processing_config_container, make_time_series_container


class TestDatasetRepository:
    def test_fetch_root_datasets(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that fetch_root_datasets returns a time series container and populates the dataset cache."""
        ts_id = "ds1"
        container = make_time_series_container(ts_id)
        mock_router = setup_mocks(ts_id, monkeypatch)
        dataset_repository = DatasetRepository(mock_router)

        assert dataset_repository._cache == {}  # cache should be empty to start

        result = dataset_repository.fetch_root_datasets("a_network", ["a_site"], ["var1"], "PT30M")

        assert result == [container]
        assert dataset_repository._cache == {ts_id: container}
        assert mock_router.fetch_dataset_by_params.call_count == 1

    def test_fetch_dataset_dependencies(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that fetch_dataset_dependencies returns a time series container and populates the dataset cache."""
        dep_ts_ids = ["ds2", "ds3"]
        mock_router = setup_mocks(dep_ts_ids, monkeypatch)
        dataset_repository = DatasetRepository(mock_router)

        assert dataset_repository._cache == {}  # cache should be empty to start

        result = dataset_repository.fetch_dataset_dependencies("ds1")

        assert result == [make_time_series_container(t) for t in dep_ts_ids]
        assert dataset_repository._cache == {t: make_time_series_container(t) for t in dep_ts_ids}
        assert mock_router.fetch_all_dependencies.call_count == 1

    def test_fetch_dataset_by_id(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that fetch_dataset_by_id returns a time series container and populates the dataset cache."""
        ts_id = "ds1"
        mock_router = setup_mocks(ts_id, monkeypatch)
        container = make_time_series_container(ts_id)
        dataset_repository = DatasetRepository(mock_router)

        assert dataset_repository._cache == {}  # cache should be empty to start

        result = dataset_repository.fetch_dataset_by_id(ts_id)
        assert result == container
        assert dataset_repository._cache == {ts_id: container}
        assert mock_router.fetch_dataset_by_id.call_count == 1

    def test_fetch_dataset_by_id_uses_cache(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that fetch_dataset_by_id uses cache and skips API call if already present."""
        ts_id = "ds1"
        mock_router = setup_mocks(ts_id, monkeypatch)
        container = make_time_series_container(ts_id)
        dataset_repository = DatasetRepository(mock_router)

        dataset_repository._cache[ts_id] = container  # mock the cache

        result = dataset_repository.fetch_dataset_by_id(ts_id)
        assert result == container
        mock_router.fetch_dataset_by_id.assert_not_called()  # shouldn't have needed to call the router functions


class TestConfigRepository:
    def test_fetch_configs_for_single_dataset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that fetch_configs_for_dataset returns data processing config."""
        ts_id = "ds1"
        mock_router = setup_mocks(ts_id, monkeypatch)
        container = make_processing_config_container(ts_id)
        config_repository = ConfigRepository(mock_router)

        result = config_repository.fetch_configs_for_dataset(ts_id)

        assert result == {ts_id: [container]}
        assert mock_router.fetch_processing_configs.call_count == 1
