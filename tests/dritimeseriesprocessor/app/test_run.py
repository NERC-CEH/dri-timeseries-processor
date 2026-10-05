from datetime import datetime
from unittest.mock import MagicMock

import pytest

from dritimeseriesprocessor.app.run import (
    _build_processor_from_graph,
    _resolve_site_label,
    run_from_config,
    run_standard,
)
from dritimeseriesprocessor.cli.selection import (
    DimensionSelection,
    HistoricSelection,
    ListSitesSelection,
    RunConfig,
)
from dritimeseriesprocessor.dag.dataset_dependency_graph import DatasetDependencyGraph
from dritimeseriesprocessor.utils.enums import CliSelectionMode

START = datetime(2024, 1, 1)
END = datetime(2024, 1, 31)


def make_graph_with_root_sites(root_site_ids: list[str]) -> DatasetDependencyGraph:
    """Create a dependency graph carrying the given root site IDs.

    Args:
        root_site_ids: The site IDs to record as the roots of the graph.

    Returns:
        A DatasetDependencyGraph with its root site IDs populated.
    """
    graph = DatasetDependencyGraph(MagicMock(), MagicMock(), MagicMock(), MagicMock())
    graph.root_site_ids = root_site_ids
    return graph


class TestResolveSiteLabel:
    def test_single_site(self) -> None:
        """Test that a single root site is returned as the label on its own."""
        graph = make_graph_with_root_sites(["site-a"])

        assert _resolve_site_label(graph) == "site-a"

    def test_multiple_sites_are_sorted_and_comma_joined(self) -> None:
        """Test that several root sites are sorted and joined into a single comma-separated label."""
        graph = make_graph_with_root_sites(["site-c", "site-a", "site-b"])

        assert _resolve_site_label(graph) == "site-a,site-b,site-c"

    def test_unknown_placeholder_is_kept(self) -> None:
        """Test that the "unknown" placeholder for a root dataset with no site is kept in the label."""
        graph = make_graph_with_root_sites(["site-a", "unknown"])

        assert _resolve_site_label(graph) == "site-a,unknown"


class TestRunFromConfig:
    @pytest.fixture
    def patched(self, monkeypatch: pytest.MonkeyPatch) -> dict[str, MagicMock]:
        """Patch out the config and the three run functions, returning them by name."""
        mocks = {
            "cfg": MagicMock(),
            "standard": MagicMock(),
            "historic": MagicMock(),
            "list_sites": MagicMock(),
        }
        monkeypatch.setattr("dritimeseriesprocessor.app.run.app_config", lambda: mocks["cfg"])
        monkeypatch.setattr("dritimeseriesprocessor.app.run.run_standard", mocks["standard"])
        monkeypatch.setattr("dritimeseriesprocessor.app.run.run_historic", mocks["historic"])
        monkeypatch.setattr("dritimeseriesprocessor.app.run.run_list_sites", mocks["list_sites"])
        return mocks

    def test_historic_mode_runs_historic_with_config(self, patched: dict[str, MagicMock]) -> None:
        """Tests that historic mode calls run_historic with its selection and the application config, and no dates."""
        selection = HistoricSelection(network="cosmos")

        run_from_config(RunConfig([selection], None, None, CliSelectionMode.HISTORIC))

        patched["historic"].assert_called_once_with(selection, patched["cfg"])
        patched["standard"].assert_not_called()
        patched["list_sites"].assert_not_called()

    def test_list_sites_mode_runs_list_sites_with_config(self, patched: dict[str, MagicMock]) -> None:
        """Tests that list-sites mode calls run_list_sites with its network, dates, config and sites."""
        selection = ListSitesSelection(network="cosmos", sites=["a-site"])

        run_from_config(RunConfig([selection], START, END, CliSelectionMode.LIST_SITES))

        patched["list_sites"].assert_called_once_with("cosmos", START, END, patched["cfg"], ["a-site"])
        patched["standard"].assert_not_called()
        patched["historic"].assert_not_called()

    @pytest.mark.parametrize(
        "mode",
        [CliSelectionMode.EXPLICIT, CliSelectionMode.CROSS_PRODUCT, CliSelectionMode.FROM_DATASETS],
    )
    def test_processing_modes_run_standard_with_config(
        self, patched: dict[str, MagicMock], mode: CliSelectionMode
    ) -> None:
        """Tests that the other modes call run_standard with their selection, dates and the application config."""
        selection = [DimensionSelection(network="cosmos")]

        run_from_config(RunConfig(selection, START, END, mode))

        patched["standard"].assert_called_once_with(selection, START, END, patched["cfg"])
        patched["historic"].assert_not_called()
        patched["list_sites"].assert_not_called()

    @pytest.mark.parametrize("mode", [CliSelectionMode.LIST_SITES, CliSelectionMode.CROSS_PRODUCT])
    @pytest.mark.parametrize("dates", [(None, END), (START, None), (None, None)])
    def test_missing_dates_are_rejected(
        self, patched: dict[str, MagicMock], mode: CliSelectionMode, dates: tuple[datetime | None, datetime | None]
    ) -> None:
        """Tests that modes which need a date range raise an error if either date is missing."""
        selection = [ListSitesSelection(network="cosmos")] if mode == CliSelectionMode.LIST_SITES else []

        with pytest.raises(ValueError, match="requires a start and end date"):
            run_from_config(RunConfig(selection, dates[0], dates[1], mode))

    def test_historic_mode_rejects_wrong_selection_type(self, patched: dict[str, MagicMock]) -> None:
        """Tests that historic mode raises an error if given a selection of another type."""
        with pytest.raises(TypeError, match="Expected HistoricSelection"):
            run_from_config(RunConfig([ListSitesSelection(network="cosmos")], None, None, CliSelectionMode.HISTORIC))

    def test_list_sites_mode_rejects_wrong_selection_type(self, patched: dict[str, MagicMock]) -> None:
        """Tests that list-sites mode raises an error if given a selection of another type."""
        with pytest.raises(TypeError, match="Expected ListSitesSelection"):
            run_from_config(RunConfig([HistoricSelection(network="cosmos")], START, END, CliSelectionMode.LIST_SITES))


class TestRunStandard:
    def test_builds_graph_and_runs_processor_for_the_date_range(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Tests that the graph and processor are built for the selection and dates, and the processor is run."""
        cfg = MagicMock(metadata_api_url="http://fake-api")
        router = MagicMock()
        build_graph = MagicMock()
        build_processor = MagicMock()
        monkeypatch.setattr("dritimeseriesprocessor.app.run.MetadataRouter", router)
        monkeypatch.setattr("dritimeseriesprocessor.app.run._build_dependency_graph", build_graph)
        monkeypatch.setattr("dritimeseriesprocessor.app.run._build_processor_from_graph", build_processor)
        selection = [DimensionSelection(network="cosmos")]

        run_standard(selection, START, END, cfg)

        router.assert_called_once_with("http://fake-api")
        build_graph.assert_called_once_with(selection, router.return_value, START, END)
        build_processor.assert_called_once_with(build_graph.return_value, START, END, cfg)
        build_processor.return_value.run.assert_called_once_with()


class TestBuildProcessorFromGraph:
    @pytest.fixture
    def metrics(self, monkeypatch: pytest.MonkeyPatch) -> MagicMock:
        """Patch out everything that connects to storage or the pushgateway, returning the Metrics mock."""
        metrics = MagicMock()
        monkeypatch.setattr("dritimeseriesprocessor.app.run.Metrics", metrics)
        for name in [
            "_build_storage",
            "create_duckdb_factory",
            "DuckDBParquetReader",
            "RawFileReader",
            "ByteParquetWriter",
            "S3DataRouter",
            "TimeSeriesProcessor",
        ]:
            monkeypatch.setattr(f"dritimeseriesprocessor.app.run.{name}", MagicMock())
        return metrics

    def test_metrics_job_name_is_unchanged_without_a_suffix(self, metrics: MagicMock) -> None:
        """Tests that the pushgateway job name is used as it is when no suffix is given."""
        cfg = MagicMock(pushgateway_url="http://gateway", pushgateway_job_name="a-job")

        _build_processor_from_graph(make_graph_with_root_sites(["site-a"]), START, END, cfg)

        metrics.assert_called_once_with("http://gateway", "a-job", site="site-a")

    def test_metrics_job_name_has_the_suffix_added(self, metrics: MagicMock) -> None:
        """Tests that a suffix is added to the pushgateway job name."""
        cfg = MagicMock(pushgateway_url="http://gateway", pushgateway_job_name="a-job")

        _build_processor_from_graph(make_graph_with_root_sites(["site-a"]), START, END, cfg, job_name_suffix="2023")

        metrics.assert_called_once_with("http://gateway", "a-job-2023", site="site-a")
