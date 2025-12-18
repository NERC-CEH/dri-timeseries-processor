from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from new_processor.dag.dataset_dependency_graph import DatasetDependencyGraph
from new_processor.models.domain_models.method_config import MethodConfig
from new_processor.models.domain_models.processing_config import ProcessingConfig, ProcessingMethodConfig
from new_processor.models.domain_models.site_metadata import SiteMetadata
from new_processor.models.domain_models.time_series_container import TimeSeriesContainer
from new_processor.utils.enums import ConfigurationType, MethodType, ProcessingLevel


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
        network="network",
        source_bucket=ts_id + "_bucket",
        source_site=ts_id + "_site",
        source_column=ts_id + "_column",
        source_dataset=ts_id + "_dataset",
        source_site_identifier=ts_id + "site_identifier",
        resolution=ts_id + "_resolution",
        periodicity=ts_id + "_periodicity",
        variable=ts_id + "_variable",
        processing_level=ProcessingLevel.PROCESSED,
        depends_on=depends_on or [],
        qc_configs=set(),
        infill_configs=set(),
        correction_configs=set(),
        method=MethodConfig(method_type=MethodType.LOAD),
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


def make_site_metadata_container(site_id: str) -> SiteMetadata:
    return SiteMetadata(
        site_id=site_id,
        alt_id="alt_it",
        full_name="full site name",
        easting=123,
        northing=456,
        lat=1.23,
        lon=4.56,
        altitude=1000,
        start_date=datetime(2000, 1, 1),
        end_date=datetime(3000, 1, 1),
    )


def create_items_list(ts_ids: str | list) -> list:
    """Create a simple list of items in a format mocking response from metadata API"""
    if isinstance(ts_ids, str):
        ts_ids = [ts_ids]
    items = [{"@id": ts_id} for ts_id in ts_ids]
    return items


def create_network_sites(site_ids: list) -> list:
    """Create a simple list of site objects mocking response from the network endpoint"""
    items = []
    for site_id in site_ids:
        site = MagicMock()
        site.id = site_id
        items.append(site)
    return items


def create_mock_router(items: list) -> MagicMock:
    """Return a mocked MetadataRouter with no-op API calls."""
    mock_router = MagicMock()

    mock_response = MagicMock()
    mock_response.items = items

    mock_router.fetch_dataset_by_params.return_value = mock_response
    mock_router.fetch_all_dependencies.return_value = mock_response
    mock_router.fetch_dataset_by_id.return_value = mock_response
    mock_router.fetch_processing_configs.return_value = mock_response
    mock_router.fetch_sites.return_value = mock_response
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
        lambda item, _, __: make_time_series_container(item["@id"]),
    )

    monkeypatch.setattr(
        "new_processor.dag.dataset_dependency_graph.map_processing_config_item",
        lambda item, _: make_processing_config_container(item["@id"]),
    )

    monkeypatch.setattr(
        "new_processor.dag.dataset_dependency_graph.map_site_metadata",
        lambda item: make_site_metadata_container(item["@id"]),
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
        builder = DatasetDependencyGraph(mock_router, "a_network", MagicMock())

        assert builder._dataset_cache == {}  # cache should be empty to start

        result = builder._fetch_root_datasets(["a_site"], ["var1"], ["PT30M"])

        assert result == [container]
        assert builder._dataset_cache == {ts_id: container}
        assert mock_router.fetch_dataset_by_params.call_count == 1

    def test_fetch_dataset_dependencies(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that _fetch_dataset_dependencies returns a time series container and populates the dataset cache."""
        dep_ts_ids = ["ds2", "ds3"]
        mock_router = setup_mocks(dep_ts_ids, monkeypatch)
        builder = DatasetDependencyGraph(mock_router, "a_network", MagicMock())

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
        builder = DatasetDependencyGraph(mock_router, "a_network", MagicMock())

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
        builder = DatasetDependencyGraph(mock_router, "a_network", MagicMock())

        builder._dataset_cache[ts_id] = container  # mock the cache

        result = builder._fetch_dataset_by_id(ts_id)
        assert result == container
        mock_router.fetch_dataset_by_id.assert_not_called()  # shouldn't have needed to call the router functions

    def test_fetch_configs_for_single_dataset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that _fetch_configs_for_dataset returns data processing config."""
        ts_id = "ds1"
        mock_router = setup_mocks(ts_id, monkeypatch)
        container = make_processing_config_container(ts_id)
        builder = DatasetDependencyGraph(mock_router, "a_network", MagicMock())

        result = builder._fetch_configs_for_dataset([ts_id])

        assert result == {ts_id: [container]}
        assert mock_router.fetch_processing_configs.call_count == 1

    @pytest.mark.parametrize(
        "sites",
        [
            (["site1"]),
            (["site1", "site2"]),
        ],
    )
    def test_get_site_metadata(self, sites: str | list, monkeypatch: pytest.MonkeyPatch) -> None:
        mock_router = setup_mocks(sites, monkeypatch)
        builder = DatasetDependencyGraph(mock_router, "a_network", MagicMock())

        builder._fetch_site_metadata(sites)
        result = builder.site_metadata

        for site_id, container in result.items():
            assert container == make_site_metadata_container(site_id)

        assert mock_router.fetch_sites.call_count == 1

    def test_get_site_metadata_no_sites(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that all sites fetched for network when no site list provided"""

        all_site_ids = ["site1", "site2", "site3"]

        mock_router = setup_mocks(all_site_ids, monkeypatch)
        mock_network_response = MagicMock()
        mock_network_response.items[0].contains = create_network_sites(all_site_ids)
        mock_router.fetch_network.return_value = mock_network_response

        builder = DatasetDependencyGraph(mock_router, "a_network", MagicMock())

        result = builder._fetch_site_metadata()

        assert result == all_site_ids

        for site_id, container in builder.site_metadata.items():
            assert container == make_site_metadata_container(site_id)

        assert mock_router.fetch_network.call_count == 1
        assert mock_router.fetch_sites.call_count == 1


class TestBuild:
    def test_resolve_dataset_single(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that a single-level dependency chain resolves correctly and configs are attached."""
        container_a = make_time_series_container("A", depends_on=["B"])
        container_b = make_time_series_container("B")

        mock_router = setup_mocks(["A", "B"], monkeypatch)

        builder = DatasetDependencyGraph(mock_router, "a_network", MagicMock())
        builder._resolve_root_datasets = MagicMock(return_value=[container_a])
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

        builder = DatasetDependencyGraph(mock_router, "a_network", MagicMock())
        builder._resolve_root_datasets = MagicMock(return_value=[container_a, container_b, container_c])
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

        builder = DatasetDependencyGraph(mock_router, "a_network", MagicMock())
        builder.datasets = {"A": container_a, "B": container_b, "C": container_c}

        dag = builder.build_dag()

        assert dag == {"A": [], "B": [], "C": []}

    def test_build_dag_simple_dependencies(self) -> None:
        """Test that a simple dependency graph maps parent to its child."""
        container_a = make_time_series_container("A", depends_on=["B"])
        container_b = make_time_series_container("B")
        container_c = make_time_series_container("C")

        mock_router = create_mock_router(["A", "B", "C"])

        builder = DatasetDependencyGraph(mock_router, "a_network", MagicMock())
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

        builder = DatasetDependencyGraph(mock_router, "a_network", MagicMock())
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
        setup_mocks(all_ids, monkeypatch)

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
                    method_configs=[ProcessingMethodConfig(method="method_with_dependency", params={"dep_ts": d})],
                    annotations={},
                )
                for d in deps
            ]
            for i, deps in config_dependencies.items()
        }
        expected_batches = [{i: containers[i] for i in batch} for batch in expected_batches]

        # Set up the DatasetDependencyGraph class object
        mock_router = create_mock_router([dataset_id for dataset_id in containers.keys()])
        builder = DatasetDependencyGraph(mock_router, "a_network", MagicMock())

        # Mock the methods that the `build` method calls with the results of the wrangling we did earlier
        builder._resolve_root_datasets = MagicMock(return_value=root_containers)
        builder._fetch_dataset_by_id = MagicMock(side_effect=lambda i: containers[i])
        builder._fetch_dataset_dependencies = MagicMock(side_effect=lambda i: direct_dependencies.get(i, []))
        builder._fetch_configs_for_dataset = MagicMock(
            side_effect=lambda i: {d: config_dependencies.get(d, []) for d in i}
        )
        builder._fetch_site_metadata = MagicMock()

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


class TestTopoSort:
    builder = DatasetDependencyGraph(MagicMock(), "a_network", MagicMock())

    test_cases_good = [
        # Flat example - A depends on B, B depends on C, C no dependencies
        pytest.param({"A": ["B"], "B": ["C"], "C": []}, [["C"], ["B"], ["A"]], id="flat A-B-C"),
        # A and B depend on C, which depends on D
        pytest.param({"A": ["C"], "B": ["C"], "C": ["D"], "D": []}, [["D"], ["C"], ["A", "B"]], id="group AB-C-D"),
        # B and C depend on A, and D depends on B and C
        pytest.param({"A": [], "B": ["A"], "C": ["A"], "D": ["B", "C"]}, [["A"], ["B", "C"], ["D"]], id="group D-BC-A"),
        # Separate graphs - A depends on B, C depends on D
        pytest.param(
            {"A": ["B"], "B": [], "C": ["D"], "D": []}, [["B", "D"], ["A", "C"]], id="separate graphs A-B C-D"
        ),
        # Three levels - A and B depend on C, C and D depend on E
        pytest.param(
            {"A": ["C"], "B": ["C"], "C": ["E"], "D": ["E"], "E": []},
            [["E"], ["C", "D"], ["A", "B"]],
            id="levels AB-C CD-E",
        ),
        # Many independent to one dependency
        pytest.param(
            {"A": ["E"], "B": ["E"], "C": ["E"], "D": ["E"], "E": []},
            [["E"], ["A", "B", "C", "D"]],
            id="one dependency ABCD-E",
        ),
    ]

    @pytest.mark.parametrize("dag, expected", test_cases_good)
    def test_flat_topo_sort(self, dag: dict, expected: list[list]) -> None:
        """Test the flat topological sorting."""
        self.builder.build_dag = MagicMock(return_value=dag)
        expected = [item for layer in expected for item in layer]
        result = self.builder.flat_topo_sort()
        assert result == expected

    @pytest.mark.parametrize("dag, expected", test_cases_good)
    def test_layered_topo_sort(self, dag: dict, expected: list[list]) -> None:
        """Test the layered topological sorting."""
        self.builder.build_dag = MagicMock(return_value=dag)
        result = self.builder.layered_topo_sort()
        assert result == expected

    test_cases_bad = [
        # Simple cycle, where both depend on each other
        pytest.param({"A": ["B"], "B": ["A"]}, id="simple cycle A-B-A"),
        # Layered cycle, where A depends on C, which depends on D, which cycles back round to depend on A
        pytest.param({"A": ["C"], "B": [], "C": ["D"], "D": ["A"]}, id="layered cycle A-C-D-A"),
    ]

    @pytest.mark.parametrize("dag", test_cases_bad)
    def test_flat_topo_sort_cycle_detected(self, dag: dict) -> None:
        """Test that error raised if a cycle detected."""
        self.builder.build_dag = MagicMock(return_value=dag)
        with pytest.raises(ValueError):
            self.builder.flat_topo_sort()

    @pytest.mark.parametrize("dag", test_cases_bad)
    def test_layered_topo_sort_cycle_detected(self, dag: dict) -> None:
        """Test that error raised if a cycle detected."""
        self.builder.build_dag = MagicMock(return_value=dag)
        with pytest.raises(ValueError):
            self.builder.layered_topo_sort()

    def test_empty_dag(self) -> None:
        """Test the sorting methods return empty list if dag is empty"""
        self.builder.build_dag = MagicMock(return_value={})
        assert self.builder.flat_topo_sort() == []
        assert self.builder.layered_topo_sort() == []
