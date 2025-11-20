from unittest.mock import MagicMock

import pytest
from dag_common import create_mock_router, setup_mocks

from new_processor.dag.batch import Batch
from new_processor.dag.dataset_dependency_graph import DatasetDependencyGraph
from new_processor.dag.repositories import DatasetRepository
from new_processor.domain_models.processing_config import MethodConfig, ProcessingConfig
from new_processor.domain_models.time_series_container import TimeSeriesContainer
from new_processor.utils.enums import ConfigurationType
from utils.fixture_helpers import make_processing_config_container, make_time_series_container


class TestResolveDataset:
    def test_resolve_dataset_single(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that a single-level dependency chain resolves correctly and configs are attached."""
        container_a = make_time_series_container("A", depends_on=["B"])
        container_b = make_time_series_container("B")

        mock_router = setup_mocks(["A", "B"], monkeypatch)

        builder = DatasetDependencyGraph("a_network", "a_site", "var1", "PT30M", mock_router)

        builder._resolve_datasets([container_a])

        # add the expected cfg into the domain models
        container_a.correction_configs = {make_processing_config_container("A")}
        container_b.correction_configs = {make_processing_config_container("B")}

        assert builder.dataset_repository.resolved == {"A": container_a, "B": container_b}
        assert mock_router.fetch_all_dependencies.call_count == 1
        assert mock_router.fetch_processing_configs.call_count == 2

    def test_resolve_dataset_multiple(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that a multi-level dependency chain resolves correctly and configs are attached."""
        container_a = make_time_series_container("A", depends_on=["B"])
        container_b = make_time_series_container("B", depends_on=["C"])
        container_c = make_time_series_container("C")

        mock_router = setup_mocks(["A", "B", "C"], monkeypatch)

        builder = DatasetDependencyGraph("a_network", "a_site", "var1", "PT30M", mock_router)

        builder._resolve_datasets([container_a, container_b, container_c])

        # add the expected cfg into the domain models
        container_a.correction_configs = {make_processing_config_container("A")}
        container_b.correction_configs = {make_processing_config_container("B")}
        container_c.correction_configs = {make_processing_config_container("C")}

        assert builder.dataset_repository.resolved == {
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

        builder = DatasetDependencyGraph("a_network", "a_site", "var1", "PT30M", MagicMock())
        builder.dataset_repository.resolved = {"A": container_a, "B": container_b, "C": container_c}

        dag = builder.build_dag()

        assert dag == {"A": [], "B": [], "C": []}

    def test_build_dag_simple_dependencies(self) -> None:
        """Test that a simple dependency graph maps parent to its child."""
        container_a = make_time_series_container("A", depends_on=["B"])
        container_b = make_time_series_container("B")
        container_c = make_time_series_container("C")

        builder = DatasetDependencyGraph("a_network", "a_site", "var1", "PT30M", MagicMock())
        builder.dataset_repository.resolved = {"A": container_a, "B": container_b, "C": container_c}

        dag = builder.build_dag()

        assert dag == {"A": ["B"], "B": [], "C": []}

    def test_build_dag_simple_nested_dependencies(self) -> None:
        """Test that a simple nested dependency graphs include all dependencies."""
        container_a = make_time_series_container("A", depends_on=["B", "C"])
        container_b = make_time_series_container("B", depends_on=["D"])
        container_c = make_time_series_container("C", depends_on=["D"])
        container_d = make_time_series_container("D")

        builder = DatasetDependencyGraph("a_network", "a_site", "var1", "PT30M", MagicMock())
        builder.dataset_repository.resolved = {"A": container_a, "B": container_b, "C": container_c, "D": container_d}

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
        builder.dataset_repository.fetch_root_datasets = MagicMock(return_value=root_containers)
        builder.dataset_repository.fetch_dataset_by_id = MagicMock(side_effect=lambda i: containers[i])
        builder.dataset_repository.fetch_dataset_dependencies = MagicMock(
            side_effect=lambda i: direct_dependencies.get(i, [])
        )
        builder.config_repository.fetch_configs_for_dataset = MagicMock(
            side_effect=lambda i: {d: config_dependencies.get(d, []) for d in i}
        )

        # We want to test which IDs are being processed in which batch, so hook into a method that captures that info
        batches = []

        def make_test_batch(initial: list[TimeSeriesContainer], repository: DatasetRepository) -> Batch:
            # Use a custom TestBatch subclass to capture the current batch contents
            class TestBatch(Batch):
                def __init__(
                    self, _initial: list[TimeSeriesContainer], _repository: DatasetRepository, _log: list
                ) -> None:
                    super().__init__(_initial, _repository)
                    self._log = _log

                def advance(self) -> None:
                    self._log.append(self.current)
                    super().advance()

            return TestBatch(initial, repository, batches)

        monkeypatch.setattr("new_processor.dag.dataset_dependency_graph.Batch", make_test_batch)

        # Do the resolving and test behaviours
        builder.build()
        assert batches == expected_batches

        dag = builder.build_dag()
        assert dag == expected_dag
