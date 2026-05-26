from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from dritimeseriesprocessor.dag.dataset_dependency_graph import DatasetDependencyGraph
from dritimeseriesprocessor.models.domain_models.processing_config import (
    DataProcessingConfig,
    DataProcessingMethodConfig,
)
from dritimeseriesprocessor.models.domain_models.site_metadata import SiteMetadata
from dritimeseriesprocessor.models.domain_models.time_series_container import TimeSeriesContainer
from dritimeseriesprocessor.utils.enums import ConfigurationType, ProcessingLevel


def make_time_series_container(
    ts_id: str,
    depends_on: list[str] | None = None,
    load_only_deps: list[str] | None = None,
) -> TimeSeriesContainer:
    """Create a lightweight fake TimeSeriesContainer for use in tests.

    Args:
        ts_id: The time series ID.
        depends_on: Optional list of dataset IDs this container depends on via dep_ts.
        load_only_deps: Optional list of dataset IDs this container depends on via load_dep_ts.

    Returns:
        A TimeSeriesContainer instance
    """
    depends_on = depends_on or []
    load_only_deps = load_only_deps or []

    method_config = None
    if depends_on or load_only_deps:
        params: dict = {}
        if depends_on:
            params["dep_ts"] = depends_on
        if load_only_deps:
            params["load_dep_ts"] = load_only_deps
        method_config = DataProcessingConfig(
            ts_id=ts_id,
            config_id=ts_id + "_cfg",
            config_type=ConfigurationType.DERIVATION,
            method_configs=[DataProcessingMethodConfig(method="m", params=params)],
            annotations={},
        )

    return TimeSeriesContainer(
        ts_id=ts_id,
        network="network",
        source_bucket=ts_id + "_bucket",
        source_site=ts_id + "_site",
        source_column=ts_id + "_column",
        source_dataset=ts_id + "_dataset",
        source_site_identifier=ts_id + "site_identifier",
        time_column_name=ts_id + "time_column_name",
        resolution=ts_id + "_resolution",
        periodicity=ts_id + "_periodicity",
        processing_level=ProcessingLevel.PROCESSED,
        qc_configs=set(),
        infill_configs=set(),
        correction_configs=set(),
        method_config=method_config,
    )


def make_processing_config_container(ts_id: str) -> DataProcessingConfig:
    """Create a lightweight fake ProcessingConfig for a given dataset.

    Args:
        ts_id: The time series ID that the configuration applies to.

    Returns:
        A ProcessingConfig instance
    """
    return DataProcessingConfig(
        ts_id=ts_id,
        config_id=ts_id + "_config_id",
        config_type=ConfigurationType.CORRECTION,
        method_configs=[],
        annotations={},
    )


def make_site_metadata_container(site_id: str) -> SiteMetadata:
    return SiteMetadata(
        site_id=site_id,
        network="a_network",
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
    items = []
    for ts_id in ts_ids:
        item = MagicMock()
        item.__getitem__ = MagicMock(side_effect=lambda key, _id=ts_id: _id)
        item.originating_site = [MagicMock(id=ts_id)]
        items.append(item)
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
    mock_router.fetch_processing_configs.return_value = mock_response
    mock_router.fetch_sites.return_value = mock_response
    mock_router.fetch_sites_by_network.return_value = mock_response

    items_dict = {item["@id"]: item for item in items}

    def capture(ids: list) -> None:
        _mock_response = MagicMock()
        _mock_response.items = [items_dict[i] for i in ids]
        return _mock_response

    mock_router.fetch_dataset_by_ids = MagicMock(side_effect=capture)

    return mock_router


def monkeypatch_api_models(monkeypatch: pytest.MonkeyPatch, items: list) -> None:
    """ "Mimic the model_validate of API pydantic models returning a list of dataset dicts"""
    api_models = ["TimeSeriesDatasetResponse"]
    api_model_return = SimpleNamespace(items=items)
    for api_model in api_models:
        monkeypatch.setattr(
            f"dritimeseriesprocessor.dag.dataset_dependency_graph.{api_model}.model_validate",
            lambda _: api_model_return,
        )


def monkeypatch_mappers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mimic the map_dataset_item Domain->API mapper returning a TimeSeriesContainer and
    Mimic the map_processing_config_item Domain->API mapper returning a ProcessingConfig
    """
    monkeypatch.setattr(
        "dritimeseriesprocessor.dag.dataset_dependency_graph.map_dataset_item",
        lambda item, _: make_time_series_container(item["@id"]),
    )

    monkeypatch.setattr(
        "dritimeseriesprocessor.dag.dataset_dependency_graph.map_processing_config_item",
        lambda item, _: make_processing_config_container(item["@id"]),
    )

    monkeypatch.setattr(
        "dritimeseriesprocessor.dag.dataset_dependency_graph.map_site_metadata",
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
        builder = DatasetDependencyGraph(mock_router, "a_network", MagicMock(), MagicMock(), MagicMock())

        assert builder._dataset_cache == {}  # cache should be empty to start

        result = builder._fetch_root_datasets(["a_site"], ["var1"], ["PT30M"])

        assert result == [container]
        assert builder._dataset_cache == {ts_id: container}
        assert mock_router.fetch_dataset_by_params.call_count == 1

    def test_fetch_configs_for_single_dataset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that _fetch_configs_for_dataset returns data processing config."""
        ts_id = "ds1"
        mock_router = setup_mocks(ts_id, monkeypatch)
        container = make_processing_config_container(ts_id)
        builder = DatasetDependencyGraph(mock_router, "a_network", MagicMock(), MagicMock(), MagicMock())

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
    def test_get_site_metadata(self, sites: list, monkeypatch: pytest.MonkeyPatch) -> None:
        mock_router = setup_mocks(sites, monkeypatch)
        builder = DatasetDependencyGraph(
            mock_router, "a_network", MagicMock(), datetime(2026, 1, 1), datetime(2026, 1, 2)
        )

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

        builder = DatasetDependencyGraph(
            mock_router, "a_network", MagicMock(), datetime(2026, 1, 1), datetime(2026, 1, 2)
        )

        result = builder._fetch_site_metadata()

        assert result == all_site_ids

        for site_id, container in builder.site_metadata.items():
            assert container == make_site_metadata_container(site_id)

        assert mock_router.fetch_sites_by_network.call_count == 1


class TestBuild:
    def test_resolve_dataset_single(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that a single-level dependency chain resolves correctly and configs are attached."""
        container_a = make_time_series_container("A", depends_on=["B"])
        container_b = make_time_series_container("B")

        mock_router = setup_mocks(["A", "B"], monkeypatch)

        builder = DatasetDependencyGraph(mock_router, "a_network", MagicMock(), MagicMock(), MagicMock())
        builder._resolve_root_datasets = MagicMock(return_value=[container_a])
        builder.build()

        # add the expected cfg into the domain models
        container_a.correction_configs = {make_processing_config_container("A")}
        container_b.correction_configs = {make_processing_config_container("B")}

        assert builder.datasets == {"A": container_a, "B": container_b}
        assert mock_router.fetch_dataset_by_ids.call_count == 1
        assert mock_router.fetch_processing_configs.call_count == 2

    def test_resolve_dataset_multiple(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that a multi-level dependency chain resolves correctly and configs are attached."""
        container_a = make_time_series_container("A", depends_on=["B"])
        container_b = make_time_series_container("B", depends_on=["C"])
        container_c = make_time_series_container("C")

        mock_router = setup_mocks(["A", "B", "C"], monkeypatch)

        builder = DatasetDependencyGraph(mock_router, "a_network", MagicMock(), MagicMock(), MagicMock())
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
        assert mock_router.fetch_dataset_by_ids.call_count == 1
        assert mock_router.fetch_processing_configs.call_count == 1


class TestEnsureSiteMetadata:
    def test_fetch_missing_site_metadata_fetches_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that a site not yet in site_metadata is fetched and cached."""
        site_id = "site1"
        mock_router = setup_mocks([site_id], monkeypatch)
        builder = DatasetDependencyGraph(mock_router, "a_network", MagicMock(), MagicMock(), MagicMock())

        assert site_id not in builder.site_metadata
        result = builder._fetch_missing_site_metadata([site_id])

        assert result == [site_id]
        assert builder.site_metadata[site_id] == make_site_metadata_container(site_id)
        mock_router.fetch_sites.assert_called_once_with([site_id])

    def test_fetch_missing_site_metadata_skips_known_sites(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that fetch_sites is not called when all requested sites are already cached."""
        site_id = "site1"
        mock_router = setup_mocks([site_id], monkeypatch)
        builder = DatasetDependencyGraph(mock_router, "a_network", MagicMock(), MagicMock(), MagicMock())
        builder.site_metadata[site_id] = make_site_metadata_container(site_id)

        result = builder._fetch_missing_site_metadata([site_id])

        assert result == []
        mock_router.fetch_sites.assert_not_called()

    def test_build_dataset_containers_calls_fetch_missing_site_metadata(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test _build_dataset_containers calls _fetch_missing_site_metadata with the site IDs from the response."""
        site_id = "site1"
        mock_router = setup_mocks(["ds1"], monkeypatch)
        builder = DatasetDependencyGraph(mock_router, "a_network", MagicMock(), MagicMock(), MagicMock())
        builder._fetch_missing_site_metadata = MagicMock()

        mock_item = MagicMock()
        mock_item.originating_site = [MagicMock(id=site_id)]
        mock_response = MagicMock()
        mock_response.items = [mock_item]

        builder._build_dataset_containers(mock_response)

        builder._fetch_missing_site_metadata.assert_called_once_with([site_id])


class TestBuildDag:
    def test_build_dag_no_dependencies(self) -> None:
        """Test that a DAG with no dependencies returns empty lists."""
        container_a = make_time_series_container("A")
        container_b = make_time_series_container("B")
        container_c = make_time_series_container("C")

        mock_router = create_mock_router([{"@id": "A"}, {"@id": "B"}, {"@id": "C"}])

        builder = DatasetDependencyGraph(mock_router, "a_network", MagicMock(), MagicMock(), MagicMock())
        builder.datasets = {"A": container_a, "B": container_b, "C": container_c}

        dag = builder.build_dag()

        assert dag == {"A": [], "B": [], "C": []}

    def test_build_dag_simple_dependencies(self) -> None:
        """Test that a simple dependency graph maps parent to its child."""
        container_a = make_time_series_container("A", depends_on=["B"])
        container_b = make_time_series_container("B")
        container_c = make_time_series_container("C")

        mock_router = create_mock_router([{"@id": "A"}, {"@id": "B"}, {"@id": "C"}])

        builder = DatasetDependencyGraph(mock_router, "a_network", MagicMock(), MagicMock(), MagicMock())
        builder.datasets = {"A": container_a, "B": container_b, "C": container_c}

        dag = builder.build_dag()

        assert dag == {"A": ["B"], "B": [], "C": []}

    def test_build_dag_simple_nested_dependencies(self) -> None:
        """Test that a simple nested dependency graphs include all dependencies."""
        container_a = make_time_series_container("A", depends_on=["B", "C"])
        container_b = make_time_series_container("B", depends_on=["D"])
        container_c = make_time_series_container("C", depends_on=["D"])
        container_d = make_time_series_container("D")

        mock_router = create_mock_router([{"@id": "A"}, {"@id": "B"}, {"@id": "C"}, {"@id": "D"}])

        builder = DatasetDependencyGraph(mock_router, "a_network", MagicMock(), MagicMock(), MagicMock())
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
                {"B": ["C"]},
                {"C": "D", "D": "A"},
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
        mock_router = setup_mocks(all_ids, monkeypatch)

        # Create TimeSeriesContainer objects for all IDs in this test
        containers = {i: make_time_series_container(i, depends_on=direct_dependencies.get(i, [])) for i in all_ids}

        # Wrangle the container objects into expected formats return by the methods we are going to mock later
        root_containers = [containers[i] for i in root_ids]
        config_dependencies = {
            i: [
                DataProcessingConfig(
                    ts_id=i,
                    config_id="config_id",
                    config_type=ConfigurationType.QUALITY_CONTROL,
                    method_configs=[DataProcessingMethodConfig(method="method_with_dependency", params={"dep_ts": d})],
                    annotations={},
                )
                for d in deps
            ]
            for i, deps in config_dependencies.items()
        }
        expected_batches = [{i: containers[i] for i in batch} for batch in expected_batches]

        # Set up the DatasetDependencyGraph class object
        builder = DatasetDependencyGraph(mock_router, "a_network", MagicMock(), MagicMock(), MagicMock())

        # Mock the methods that the `build` method calls with the results of the wrangling we did earlier
        builder._resolve_root_datasets = MagicMock(return_value=root_containers)
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
        assert [b.keys() for b in batches] == [b.keys() for b in expected_batches]

        dag = builder.build_dag()
        assert dag == expected_dag


class TestTopoSort:
    builder = DatasetDependencyGraph(MagicMock(), "a_network", MagicMock(), MagicMock(), MagicMock())

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


class TestLoadOnlyDependencies:
    def test_load_only_dep_is_flagged_as_load_only(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A dep referenced only via load_dep_ts is added to datasets with load_only=True."""
        container_a = make_time_series_container("A", load_only_deps=["L"])
        mock_router = setup_mocks(["A", "L"], monkeypatch)
        builder = DatasetDependencyGraph(mock_router, "a_network", MagicMock(), MagicMock(), MagicMock())
        builder._resolve_root_datasets = MagicMock(return_value=[container_a])
        builder.build()

        assert "L" in builder.datasets
        assert builder.datasets["L"].load_only is True

    def test_load_only_dep_has_no_configs_attached(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A load-only dep goes into datasets with no configs (method_config=None, empty config sets)."""
        container_a = make_time_series_container("A", load_only_deps=["L"])
        mock_router = setup_mocks(["A", "L"], monkeypatch)
        builder = DatasetDependencyGraph(mock_router, "a_network", MagicMock(), MagicMock(), MagicMock())
        builder._resolve_root_datasets = MagicMock(return_value=[container_a])
        builder.build()

        dep = builder.datasets["L"]
        assert dep.method_config is None
        assert dep.correction_configs == set()
        assert dep.qc_configs == set()
        assert dep.infill_configs == set()

    def test_fetch_processing_configs_not_called_for_load_only(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """fetch_processing_configs must never be called with a load-only ID."""
        container_a = make_time_series_container("A", load_only_deps=["L"])
        mock_router = setup_mocks(["A", "L"], monkeypatch)
        builder = DatasetDependencyGraph(mock_router, "a_network", MagicMock(), MagicMock(), MagicMock())
        builder._resolve_root_datasets = MagicMock(return_value=[container_a])
        builder.build()

        for call in mock_router.fetch_processing_configs.call_args_list:
            assert "L" not in call[0][0]

    def test_load_only_dep_no_deps_resolved(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Tests that a load-only dependency does not have it's own dependencies resolved"""
        container_a = make_time_series_container("A", load_only_deps=["L"])
        mock_router = setup_mocks(["A", "L"], monkeypatch)
        builder = DatasetDependencyGraph(mock_router, "a_network", MagicMock(), MagicMock(), MagicMock())
        builder._resolve_root_datasets = MagicMock(return_value=[container_a])

        config_deps = {
            "L": [
                DataProcessingConfig(
                    ts_id="L",
                    config_id="L_cfg",
                    config_type=ConfigurationType.QUALITY_CONTROL,
                    method_configs=[DataProcessingMethodConfig(method="m", params={"dep_ts": "M"})],
                    annotations={},
                )
            ]
        }
        builder._fetch_configs_for_dataset = MagicMock(side_effect=lambda ids: {i: config_deps.get(i, []) for i in ids})
        builder.build()

        assert "M" not in builder.datasets

    def test_reset_clears_load_dep_and_dep_ts_ids(self) -> None:
        """Test that reset() clears the classification sets for load-only and normal deps."""
        builder = DatasetDependencyGraph(MagicMock(), "a_network", MagicMock(), MagicMock(), MagicMock())
        builder._dep_ts_ids.add("A")
        builder._load_dep_ts_ids.add("L")
        builder.reset()
        assert builder._dep_ts_ids == set()
        assert builder._load_dep_ts_ids == set()

    def test_dep_ts_vs_load_dep_ts_conflict(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When A references L via load_dep_ts and B references L via dep_ts in the same batch, L is not load-only.
        i.e. the dep_ts reference wins
        """
        container_a = make_time_series_container("A", load_only_deps=["L"])
        container_b = make_time_series_container("B", depends_on=["L"])
        mock_router = setup_mocks(["A", "B", "L"], monkeypatch)
        builder = DatasetDependencyGraph(mock_router, "a_network", MagicMock(), MagicMock(), MagicMock())
        builder._resolve_root_datasets = MagicMock(return_value=[container_a, container_b])
        builder.build()

        assert "L" in builder.datasets
        assert builder.datasets["L"].load_only is False

    def test_load_dep_ts_vs_dep_ts_update(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """If L is initially resolved as load-only but then encountered via dep_ts in a later batch, it is
        re-queued for full processing and ends up with load_only=False."""
        # A loads L as load-only. B depends on C which depends on L via dep_ts.
        container_a = make_time_series_container("A", load_only_deps=["L"])
        container_b = make_time_series_container("B", depends_on=["C"])
        mock_router = setup_mocks(["A", "B", "C", "L"], monkeypatch)

        builder = DatasetDependencyGraph(mock_router, "a_network", MagicMock(), MagicMock(), MagicMock())
        builder._resolve_root_datasets = MagicMock(return_value=[container_a, container_b])

        config_deps = {
            "C": [
                DataProcessingConfig(
                    ts_id="C",
                    config_id="C_cfg",
                    config_type=ConfigurationType.QUALITY_CONTROL,
                    method_configs=[DataProcessingMethodConfig(method="m", params={"dep_ts": "L"})],
                    annotations={},
                )
            ]
        }
        builder._fetch_configs_for_dataset = MagicMock(side_effect=lambda ids: {i: config_deps.get(i, []) for i in ids})
        builder.build()

        assert "L" in builder.datasets
        assert builder.datasets["L"].load_only is False
