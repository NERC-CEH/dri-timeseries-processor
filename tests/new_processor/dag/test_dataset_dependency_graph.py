from types import SimpleNamespace
from typing import Callable
from unittest.mock import MagicMock

import pytest

from new_processor.dag.dataset_dependency_graph import DatasetDependencyGraph
from new_processor.domain_models.processing_config import ProcessingConfig
from new_processor.domain_models.time_series_container import TimeSeriesContainer
from new_processor.utils.enums import ConfigurationType, ProcessingLevel


def make_time_series_container(ts_id: str, depends_on: list[str] | None = None) -> TimeSeriesContainer:
    """Create a lightweight fake TimeSeriesContainer for use in tests.

    Args:
        ts_id: The time series ID.
        depends_on: Optional list of dataset IDs that this container depends on.

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
        processing_level=ProcessingLevel.PROCESSED,
        depends_on=depends_on or [],
        qc_configs=[],
        infill_configs=[],
        correction_configs=[],
    )


def make_processing_config_container(ts_id: str) -> ProcessingConfig:
    """Create a lightweight fake ProcessingConfig for a given dataset.

    Args:
        ts_id: The time series ID that the configuration applies to.

    Returns:
        A ProcessingConfig instance
    """
    return ProcessingConfig(
        ts_id=ts_id,
        config_id=ts_id + "_config_id",
        config_type=ConfigurationType.CORRECTION,
        method_configs=[],
        annotations={},
    )


@pytest.fixture
def mock_router() -> MagicMock:
    """Return a mocked MetadataRouter with no-op API calls."""
    router = MagicMock()
    router.fetch_dataset_by_params.return_value = {"items": []}
    router.fetch_all_dependencies.return_value = {"items": []}
    router.fetch_dataset_by_id.return_value = {"items": []}
    router.fetch_processing_configs.return_value = {"items": []}
    return router


@pytest.fixture
def patch_dataset_model_and_mapper(
    mock_router: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> Callable[[str | list[str]], None]:
    """Fixture to patch Pydantic model validators and mapping functions."""

    def _apply(ts_id: str) -> None:
        if isinstance(ts_id, str):
            ts_id = [ts_id]
        items = [{"@id": t} for t in ts_id]
        api_model_return = SimpleNamespace(items=items)

        # Fake API returns
        mock_router.fetch_dataset_by_params.return_value = {"items": items}
        mock_router.fetch_all_dependencies.return_value = {"items": items}
        mock_router.fetch_dataset_by_id.return_value = {"items": items}
        mock_router.fetch_processing_configs.return_value = {"items": items}

        # Mimic the model_validate of API pydantic models returning a list of dataset dicts
        api_models = ["TimeSeriesDatasetResponse", "DataProcessingConfiguration"]
        for api_model in api_models:
            monkeypatch.setattr(
                f"new_processor.dag.dataset_dependency_graph.{api_model}.model_validate", lambda _: api_model_return
            )

        # Mimic the map_dataset_item Domain->API mapper returning a TimeSeriesContainer
        monkeypatch.setattr(
            "new_processor.dag.dataset_dependency_graph.map_dataset_item",
            lambda item: make_time_series_container(item["@id"]),
        )

        # Mimic the map_processing_config_item Domain->API mapper returning a ProcessingConfig
        monkeypatch.setattr(
            "new_processor.dag.dataset_dependency_graph.map_processing_config_item",
            lambda item: make_processing_config_container(item["@id"]),
        )

    return _apply


class TestFetchDatasets:
    def test_fetch_root_datasets(self, mock_router: MagicMock, patch_dataset_model_and_mapper: Callable) -> None:
        """Test that _fetch_root_datasets returns a time series container and populates the dataset cache."""
        ts_id = "ds1"
        container = make_time_series_container("ds1")
        patch_dataset_model_and_mapper(ts_id)
        builder = DatasetDependencyGraph("a_network", "a_site", "var1", "PT30M", mock_router)

        assert builder._dataset_cache == {}  # cache should be empty to start

        result = builder._fetch_root_datasets()

        assert result == [container]
        assert builder._dataset_cache == {ts_id: container}
        assert mock_router.fetch_dataset_by_params.call_count == 1

    def test_fetch_dataset_dependencies(self, mock_router: MagicMock, patch_dataset_model_and_mapper: Callable) -> None:
        """Test that _fetch_dataset_dependencies returns a time series container and populates the dataset cache."""
        dep_ts_ids = ["ds2", "ds3"]
        patch_dataset_model_and_mapper(dep_ts_ids)
        builder = DatasetDependencyGraph("a_network", "a_site", "var1", "PT30M", mock_router)

        assert builder._dataset_cache == {}  # cache should be empty to start

        result = builder._fetch_dataset_dependencies("ds1")

        assert result == [make_time_series_container(t) for t in dep_ts_ids]
        assert builder._dataset_cache == {t: make_time_series_container(t) for t in dep_ts_ids}
        assert mock_router.fetch_all_dependencies.call_count == 1

    def test_fetch_dataset_by_id(self, mock_router: MagicMock, patch_dataset_model_and_mapper: Callable) -> None:
        """Test that _fetch_dataset_by_id returns a time series container and populates the dataset cache."""
        ts_id = "ds1"
        patch_dataset_model_and_mapper(ts_id)
        container = make_time_series_container(ts_id)
        builder = DatasetDependencyGraph("a_network", "a_site", "var1", "PT30M", mock_router)

        assert builder._dataset_cache == {}  # cache should be empty to start

        result = builder._fetch_dataset_by_id(ts_id)
        assert result == container
        assert builder._dataset_cache == {ts_id: container}
        assert mock_router.fetch_dataset_by_id.call_count == 1

    def test_fetch_dataset_by_id_uses_cache(
        self, mock_router: MagicMock, patch_dataset_model_and_mapper: Callable
    ) -> None:
        """Test that _fetch_dataset_by_id uses cache and skips API call if already present."""
        ts_id = "ds1"
        patch_dataset_model_and_mapper(ts_id)
        container = make_time_series_container(ts_id)
        builder = DatasetDependencyGraph("a_network", "a_site", "var1", "PT30M", mock_router)

        builder._dataset_cache[ts_id] = container  # mock the cache

        result = builder._fetch_dataset_by_id(ts_id)
        assert result == container
        mock_router.fetch_dataset_by_id.assert_not_called()  # shouldn't have needed to call the router functions

    def test_fetch_configs_for_single_dataset(
        self, mock_router: MagicMock, patch_dataset_model_and_mapper: Callable
    ) -> None:
        """Test that _fetch_configs_for_dataset returns data processing config."""
        ts_id = "ds1"
        patch_dataset_model_and_mapper(ts_id)
        container = make_processing_config_container(ts_id)
        builder = DatasetDependencyGraph("a_network", "a_site", "var1", "PT30M", mock_router)

        result = builder._fetch_configs_for_dataset(ts_id)

        assert result == {ts_id: [container]}
        assert mock_router.fetch_processing_configs.call_count == 1


class TestResolveDataset:
    def test_resolve_dataset_single(self, mock_router: MagicMock, patch_dataset_model_and_mapper: Callable) -> None:
        """Test that a single-level dependency chain resolves correctly and configs are attached."""
        container_a = make_time_series_container("A", depends_on=["B"])
        container_b = make_time_series_container("B")

        patch_dataset_model_and_mapper(["A", "B"])

        builder = DatasetDependencyGraph("a_network", "a_site", "var1", "PT30M", mock_router)

        builder._resolve_dataset([container_a])

        # add the expected cfg into the domain models
        container_a.correction_configs = [make_processing_config_container("A")]
        container_b.correction_configs = [make_processing_config_container("B")]

        assert builder.datasets == {"A": container_a, "B": container_b}
        assert mock_router.fetch_all_dependencies.call_count == 1
        assert mock_router.fetch_processing_configs.call_count == 2

    def test_resolve_dataset_multiple(self, mock_router: MagicMock, patch_dataset_model_and_mapper: Callable) -> None:
        """Test that a multi-level dependency chain resolves correctly and configs are attached."""
        container_a = make_time_series_container("A", depends_on=["B"])
        container_b = make_time_series_container("B", depends_on=["C"])
        container_c = make_time_series_container("C")

        patch_dataset_model_and_mapper(["A", "B", "C"])

        builder = DatasetDependencyGraph("a_network", "a_site", "var1", "PT30M", mock_router)

        builder._resolve_dataset([container_a, container_b, container_c])

        # add the expected cfg into the domain models
        container_a.correction_configs = [make_processing_config_container("A")]
        container_b.correction_configs = [make_processing_config_container("B")]
        container_c.correction_configs = [make_processing_config_container("C")]

        assert builder.datasets == {
            "A": container_a,
            "B": container_b,
            "C": container_c,
        }
        assert mock_router.fetch_all_dependencies.call_count == 2
        assert mock_router.fetch_processing_configs.call_count == 1


class TestBuildDag:
    def test_build_dag_no_dependencies(self, mock_router: MagicMock) -> None:
        """Test that a DAG with no dependencies returns empty lists."""
        container_a = make_time_series_container("A")
        container_b = make_time_series_container("B")
        container_c = make_time_series_container("C")

        builder = DatasetDependencyGraph("a_network", "a_site", "var1", "PT30M", mock_router)
        builder.datasets = {"A": container_a, "B": container_b, "C": container_c}

        dag = builder.build_dag()

        assert dag == {"A": [], "B": [], "C": []}

    def test_build_dag_simple_dependencies(self, mock_router: MagicMock) -> None:
        """Test that a simple dependency graph maps parent to its child."""
        container_a = make_time_series_container("A", depends_on=["B"])
        container_b = make_time_series_container("B")
        container_c = make_time_series_container("C")

        builder = DatasetDependencyGraph("a_network", "a_site", "var1", "PT30M", mock_router)
        builder.datasets = {"A": container_a, "B": container_b, "C": container_c}

        dag = builder.build_dag()

        assert dag == {"A": ["B"], "B": [], "C": []}

    def test_build_dag_nested_dependencies(self, mock_router: MagicMock) -> None:
        """Test that nested dependency graphs include all dependencies."""
        container_a = make_time_series_container("A", depends_on=["B", "C"])
        container_b = make_time_series_container("B", depends_on=["D"])
        container_c = make_time_series_container("C", depends_on=["D"])
        container_d = make_time_series_container("D")

        builder = DatasetDependencyGraph("a_network", "a_site", "var1", "PT30M", mock_router)
        builder.datasets = {"A": container_a, "B": container_b, "C": container_c, "D": container_d}

        dag = builder.build_dag()

        assert dag == {"A": ["B", "C"], "B": ["D"], "C": ["D"], "D": []}
