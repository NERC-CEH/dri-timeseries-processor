from unittest.mock import MagicMock

from dritimeseriesprocessor.app.run import _resolve_site_label
from dritimeseriesprocessor.dag.dataset_dependency_graph import DatasetDependencyGraph


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
