from collections import Counter

from new_processor.cli.selection import CrossProductSelectionSpec, ExplicitSelectionSpec, RootQuery


class TestExplicitSelectionSpec:
    def test_explicit_queries(self) -> None:
        """Test that explicit query list is returned as expected"""
        queries = [
            RootQuery(sites=["A"], variables=["TA"], periodicities=["P1D"]),
            RootQuery(sites=["B"], variables=["RH"], periodicities=["PT30M"]),
        ]
        spec = ExplicitSelectionSpec(queries)
        assert Counter(spec.root_queries) == Counter(queries)

    def test_deduplicates_identical_queries(self) -> None:
        """Test that requesting the same set query gets deduplicated"""
        query = RootQuery(sites=["A"], variables=["TA"], periodicities=["P1D"])
        spec = ExplicitSelectionSpec([query, query])
        assert spec.root_queries == [query]


class TestCrossProductSelectionSpec:
    def test_single_root_query(self) -> None:
        """Test that single root query is returned as expected"""
        sites = ["A", "B"]
        variables = ["TA"]
        periodicities = ["P1D"]

        spec = CrossProductSelectionSpec(sites, variables, periodicities)
        expected = [RootQuery(sites, variables, periodicities)]

        assert spec.root_queries == expected

    def test_none_args(self) -> None:
        """Test that providing "none" args is preserved"""
        spec = CrossProductSelectionSpec()
        expected = [RootQuery()]

        assert spec.root_queries == expected
        assert spec.root_queries[0].sites is None
        assert spec.root_queries[0].variables is None
        assert spec.root_queries[0].periodicities is None

    def test_empty_lists(self) -> None:
        """Test that providing empty list args is preserved"""
        spec = CrossProductSelectionSpec(sites=[], variables=[], periodicities=[])
        expected = [RootQuery([], [], [])]

        assert spec.root_queries == expected
        assert spec.root_queries[0].sites == []
        assert spec.root_queries[0].variables == []
        assert spec.root_queries[0].periodicities == []
