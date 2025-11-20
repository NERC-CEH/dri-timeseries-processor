from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from new_processor.dag.dataset_dependency_graph import DatasetDependencyGraph
from new_processor.domain_models.processing_config import MethodConfig, ProcessingConfig
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
        qc_configs=set(),
        infill_configs=set(),
        correction_configs=set(),
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


def create_items_list(ts_ids: str | list) -> list:
    """Create a simple list of items in a format mocking response from metadata API"""
    if isinstance(ts_ids, str):
        ts_ids = [ts_ids]
    items = [{"@id": ts_id} for ts_id in ts_ids]
    return items


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
        monkeypatch.setattr(
            f"new_processor.dag.dataset_dependency_graph.{api_model}.model_validate", lambda _: api_model_return
        )


def monkeypatch_mappers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mimic the map_dataset_item Domain->API mapper returning a TimeSeriesContainer and
    Mimic the map_processing_config_item Domain->API mapper returning a ProcessingConfig
    """
    monkeypatch.setattr(
        "new_processor.dag.dataset_dependency_graph.map_dataset_item",
        lambda item: make_time_series_container(item["@id"]),
    )

    monkeypatch.setattr(
        "new_processor.dag.dataset_dependency_graph.map_processing_config_item",
        lambda item: make_processing_config_container(item["@id"]),
    )


def setup_mocks(ts_ids: str | list[str], monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Mock the pydantic model validators and mapping functions."""
    items = create_items_list(ts_ids)
    mock_router = create_mock_router(items)
    monkeypatch_api_models(monkeypatch, items)
    monkeypatch_mappers(monkeypatch)
    return mock_router


class TestFetchDatasets:
    def test_fetch_root_datasets(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that _fetch_root_datasets returns a time series container and populates the dataset cache."""
        ts_id = "ds1"
        container = make_time_series_container("ds1")
        mock_router = setup_mocks(ts_id, monkeypatch)
        builder = DatasetDependencyGraph("a_network", "a_site", "var1", "PT30M", mock_router)

        assert builder._dataset_cache == {}  # cache should be empty to start

        result = builder._fetch_root_datasets()

        assert result == [container]
        assert builder._dataset_cache == {ts_id: container}
        assert mock_router.fetch_dataset_by_params.call_count == 1

    def test_fetch_dataset_dependencies(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that _fetch_dataset_dependencies returns a time series container and populates the dataset cache."""
        dep_ts_ids = ["ds2", "ds3"]
        mock_router = setup_mocks(dep_ts_ids, monkeypatch)
        builder = DatasetDependencyGraph("a_network", "a_site", "var1", "PT30M", mock_router)

        assert builder._dataset_cache == {}  # cache should be empty to start

        result = builder._fetch_dataset_dependencies("ds1")

        assert result == [make_time_series_container(t) for t in dep_ts_ids]
        assert builder._dataset_cache == {t: make_time_series_container(t) for t in dep_ts_ids}
        assert mock_router.fetch_all_dependencies.call_count == 1

    def test_fetch_dataset_by_id(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that _fetch_dataset_by_id returns a time series container and populates the dataset cache."""
        ts_id = "ds1"
        mock_router = setup_mocks(ts_id, monkeypatch)
        container = make_time_series_container(ts_id)
        builder = DatasetDependencyGraph("a_network", "a_site", "var1", "PT30M", mock_router)

        assert builder._dataset_cache == {}  # cache should be empty to start

        result = builder._fetch_dataset_by_id(ts_id)
        assert result == container
        assert builder._dataset_cache == {ts_id: container}
        assert mock_router.fetch_dataset_by_id.call_count == 1

    def test_fetch_dataset_by_id_uses_cache(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that _fetch_dataset_by_id uses cache and skips API call if already present."""
        ts_id = "ds1"
        mock_router = setup_mocks(ts_id, monkeypatch)
        container = make_time_series_container(ts_id)
        builder = DatasetDependencyGraph("a_network", "a_site", "var1", "PT30M", mock_router)

        builder._dataset_cache[ts_id] = container  # mock the cache

        result = builder._fetch_dataset_by_id(ts_id)
        assert result == container
        mock_router.fetch_dataset_by_id.assert_not_called()  # shouldn't have needed to call the router functions

    def test_fetch_configs_for_single_dataset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that _fetch_configs_for_dataset returns data processing config."""
        ts_id = "ds1"
        mock_router = setup_mocks(ts_id, monkeypatch)
        container = make_processing_config_container(ts_id)
        builder = DatasetDependencyGraph("a_network", "a_site", "var1", "PT30M", mock_router)

        result = builder._fetch_configs_for_dataset(ts_id)

        assert result == {ts_id: [container]}
        assert mock_router.fetch_processing_configs.call_count == 1


class TestBuild:
    def test_resolve_dataset_single(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that a single-level dependency chain resolves correctly and configs are attached."""
        container_a = make_time_series_container("A", depends_on=["B"])
        container_b = make_time_series_container("B")

        mock_router = setup_mocks(["A", "B"], monkeypatch)

        builder = DatasetDependencyGraph("a_network", "a_site", "var1", "PT30M", mock_router)
        builder._fetch_root_datasets = MagicMock(return_value=[container_a])
        builder.build()

        # add the expected cfg into the domain models
        container_a.correction_configs = {make_processing_config_container("A")}
        container_b.correction_configs = {make_processing_config_container("B")}

        assert builder.datasets == {"A": container_a, "B": container_b}
        assert mock_router.fetch_all_dependencies.call_count == 1
        assert mock_router.fetch_processing_configs.call_count == 2

    def test_resolve_dataset_multiple(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that a multi-level dependency chain resolves correctly and configs are attached."""
        container_a = make_time_series_container("A", depends_on=["B"])
        container_b = make_time_series_container("B", depends_on=["C"])
        container_c = make_time_series_container("C")

        mock_router = setup_mocks(["A", "B", "C"], monkeypatch)

        builder = DatasetDependencyGraph("a_network", "a_site", "var1", "PT30M", mock_router)
        builder._fetch_root_datasets = MagicMock(return_value=[container_a, container_b, container_c])
        builder.build()

        # add the expected cfg into the domain models
        container_a.correction_configs = {make_processing_config_container("A")}
        container_b.correction_configs = {make_processing_config_container("B")}
        container_c.correction_configs = {make_processing_config_container("C")}

        assert builder.datasets == {
            "A": container_a,
            "B": container_b,
            "C": container_c,
        }
        assert mock_router.fetch_all_dependencies.call_count == 2
        assert mock_router.fetch_processing_configs.call_count == 1


class TestBuildDag:
    def test_build_dag_no_dependencies(self) -> None:
        """Test that a DAG with no dependencies returns empty lists."""
        container_a = make_time_series_container("A")
        container_b = make_time_series_container("B")
        container_c = make_time_series_container("C")

        mock_router = create_mock_router(["A", "B", "C"])

        builder = DatasetDependencyGraph("a_network", "a_site", "var1", "PT30M", mock_router)
        builder.datasets = {"A": container_a, "B": container_b, "C": container_c}

        dag = builder.build_dag()

        assert dag == {"A": [], "B": [], "C": []}

    def test_build_dag_simple_dependencies(self) -> None:
        """Test that a simple dependency graph maps parent to its child."""
        container_a = make_time_series_container("A", depends_on=["B"])
        container_b = make_time_series_container("B")
        container_c = make_time_series_container("C")

        mock_router = create_mock_router(["A", "B", "C"])

        builder = DatasetDependencyGraph("a_network", "a_site", "var1", "PT30M", mock_router)
        builder.datasets = {"A": container_a, "B": container_b, "C": container_c}

        dag = builder.build_dag()

        assert dag == {"A": ["B"], "B": [], "C": []}

    def test_build_dag_simple_nested_dependencies(self) -> None:
        """Test that a simple nested dependency graphs include all dependencies."""
        container_a = make_time_series_container("A", depends_on=["B", "C"])
        container_b = make_time_series_container("B", depends_on=["D"])
        container_c = make_time_series_container("C", depends_on=["D"])
        container_d = make_time_series_container("D")

        mock_router = create_mock_router(["A", "B", "C", "D"])

        builder = DatasetDependencyGraph("a_network", "a_site", "var1", "PT30M", mock_router)
        builder.datasets = {"A": container_a, "B": container_b, "C": container_c, "D": container_d}

        dag = builder.build_dag()

        assert dag == {"A": ["B", "C"], "B": ["D"], "C": ["D"], "D": []}


class TestBuildResolver:
    @pytest.mark.parametrize(
        "all_ids, root_ids, direct_dependencies, config_dependencies, expected_batches, expected_dag",
        [
            (
                # Scenario 1
                # ----------
                # Setup:
                #   - A as root dataset
                #   - A depends on B
                #   - B depends on C via a config
                # Expected behaviour:
                #   - A should be in batch 1,
                #   - B should be in batch 2
                #   - C in batch 3
                ["A", "B", "C"],
                ["A"],
                {"A": ["B"]},
                {"B": ["C"]},
                [["A"], ["B"], ["C"]],
                {"A": ["B"], "B": ["C"], "C": []},
            ),
            (
                # Scenario 2
                # ----------
                # Setup:
                #   - A, B as root datasets
                #   - B depends on C
                #   - C depends on D via a config
                #   - D depends on A (to check the deeper levels of recursion)
                # Expected behaviour:
                #   - A, B should be in batch 1,
                #   - C should be in batch 2
                #   - D in batch 3
                #   - A would be in next batch, but should exit early as A already resolved.
                ["A", "B", "C", "D"],
                ["A", "B"],
                {"B": ["C"], "D": ["A"]},
                {"C": "D"},
                [["A", "B"], ["C"], ["D"]],
                {"A": [], "B": ["C"], "C": ["D"], "D": ["A"]},
            ),
            (
                # Scenario 3
                # ----------
                # Setup:
                #   - A and D as root datasets
                #   - A depends on B, C, D
                #   - B and C depends on D via a config
                #   - D depends on B
                # Expected behaviour:
                #   - A, D should be in batch 1,
                #   - B, C should be in batch 2, along with D (as it's a dep of A, and hasn't been processed yet)
                #   - No more batches as everything processed by now.
                ["A", "B", "C", "D"],
                ["A", "D"],
                {"A": ["B", "C", "D"], "D": ["B"]},
                {"B": ["D"], "C": ["D"]},
                [["A", "D"], ["B", "C", "D"]],
                {"A": ["B", "C", "D"], "B": ["D"], "C": ["D"], "D": ["B"]},
            ),
        ],
    )
    def test_build_scenarios(
        self,
        all_ids: list,
        root_ids: list,
        direct_dependencies: dict,
        config_dependencies: dict,
        expected_batches: list,
        expected_dag: dict,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test scenario for the dataset dependency graph resolver."""

        # Create TimeSeriesContainer objects for all IDs in this test
        containers = {i: make_time_series_container(i, depends_on=direct_dependencies.get(i, [])) for i in all_ids}

        # Wrangle the container objects into expected formats return by the methods we are going to mock later
        root_containers = [containers[i] for i in root_ids]
        direct_dependencies = {i: [containers[d] for d in deps] for i, deps in direct_dependencies.items()}
        config_dependencies = {
            i: [
                ProcessingConfig(
                    ts_id=i,
                    config_id="config_id",
                    config_type=ConfigurationType.QUALITY_CONTROL,
                    method_configs=[MethodConfig(method="method_with_dependency", params={"dep_ts": d})],
                    annotations={},
                )
                for d in deps
            ]
            for i, deps in config_dependencies.items()
        }
        expected_batches = [{i: containers[i] for i in batch} for batch in expected_batches]

        # Set up the DatasetDependencyGraph class object
        mock_router = create_mock_router([dataset_id for dataset_id in containers.keys()])
        builder = DatasetDependencyGraph("a_network", "a_site", "A", "PT30M", mock_router)

        # Mock the methods that the `build` method calls with the results of the wrangling we did earlier
        builder._fetch_root_datasets = MagicMock(return_value=root_containers)
        builder._fetch_dataset_by_id = MagicMock(side_effect=lambda i: containers[i])
        builder._fetch_dataset_dependencies = MagicMock(side_effect=lambda i: direct_dependencies.get(i, []))
        builder._fetch_configs_for_dataset = MagicMock(
            side_effect=lambda i: {d: config_dependencies.get(d, []) for d in i}
        )

        # We want to test which IDs are being processed in which batch, so hook into a method that captures that info
        batches = []

        def capture(batch: dict) -> None:
            batches.append(batch)

        builder._batch_start = MagicMock(side_effect=capture)

        # Do the resolving and test behaviours
        builder.build()
        assert batches == expected_batches

        dag = builder.build_dag()
        assert dag == expected_dag
