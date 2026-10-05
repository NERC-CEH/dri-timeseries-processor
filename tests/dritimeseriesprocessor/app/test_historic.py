from datetime import datetime
from unittest.mock import MagicMock

import pytest
from freezegun import freeze_time

from dritimeseriesprocessor.app.run import run_historic
from dritimeseriesprocessor.cli.selection import DimensionSelection, HistoricSelection
from dritimeseriesprocessor.models.domain_models.site_metadata import SiteMetadata
from dritimeseriesprocessor.utils.urls import PROGRAMME_URI, SITE_URI

CONFIG = MagicMock(metadata_api_url="http://fake-api")


@freeze_time("2024-03-10")
class TestRunHistoric:
    @staticmethod
    def _site(
        name: str, start: datetime | None, end: datetime | None = None, network: str = f"{PROGRAMME_URI}/cosmos"
    ) -> SiteMetadata:
        return SiteMetadata(site_id=f"{SITE_URI}/{name}", network=network, start_date=start, end_date=end)

    def _setup(self, monkeypatch: pytest.MonkeyPatch, sites: list[SiteMetadata]) -> MagicMock:
        """Patch out metadata and processing; return the mock used to build each chunk's processor."""
        monkeypatch.setattr(
            "dritimeseriesprocessor.app.run._fetch_network_sites", lambda _router, _network, _sites=None: sites
        )
        self.build_graph = MagicMock()
        monkeypatch.setattr("dritimeseriesprocessor.app.run._build_dependency_graph", self.build_graph)
        build_processor = MagicMock()
        monkeypatch.setattr("dritimeseriesprocessor.app.run._build_processor_from_graph", build_processor)
        return build_processor

    def test_open_site_runs_each_year_up_to_today(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Tests that a site with no end date is processed one year at a time from its start year up to today."""
        build_processor = self._setup(monkeypatch, [self._site("cosmos-alic1", datetime(2022, 7, 1))])

        run_historic(HistoricSelection(network="cosmos"), CONFIG)

        windows = [call.args[1:3] for call in build_processor.call_args_list]
        assert windows == [
            (datetime(2022, 7, 1), datetime(2022, 12, 31)),
            (datetime(2023, 1, 1), datetime(2023, 12, 31)),
            (datetime(2024, 1, 1), datetime(2024, 3, 10)),
        ]

    def test_closed_site_stops_at_its_end_date(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Tests that a closed site is processed only up to its end date."""
        site = self._site("cosmos-alic1", datetime(2020, 1, 1), datetime(2021, 5, 1))
        build_processor = self._setup(monkeypatch, [site])

        run_historic(HistoricSelection(network="cosmos"), CONFIG)

        windows = [call.args[1:3] for call in build_processor.call_args_list]
        assert windows == [
            (datetime(2020, 1, 1), datetime(2020, 12, 31)),
            (datetime(2021, 1, 1), datetime(2021, 5, 1)),
        ]

    def test_site_without_start_date_is_skipped_and_reported(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Tests that a site with no start date is skipped, the others still run, and the run raises at the end."""
        sites = [self._site("cosmos-nostart", None), self._site("cosmos-alic1", datetime(2024, 1, 1))]
        build_processor = self._setup(monkeypatch, sites)

        with pytest.raises(RuntimeError, match="cosmos-nostart"):
            run_historic(HistoricSelection(network="cosmos"), CONFIG)

        assert build_processor.call_count == 1

    def test_failed_year_does_not_stop_remaining_years(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Tests that a year that fails is reported at the end while later years still run."""
        build_processor = self._setup(monkeypatch, [self._site("cosmos-alic1", datetime(2023, 1, 1))])
        build_processor.return_value.run.side_effect = [RuntimeError("boom"), None]

        with pytest.raises(RuntimeError, match="2023-01-01 to 2023-12-31"):
            run_historic(HistoricSelection(network="cosmos"), CONFIG)

        assert build_processor.call_count == 2

    def test_graph_is_built_for_each_year_for_the_site(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Tests that a new dependency graph is built for each year, selecting just that site over its full dates."""
        self._setup(monkeypatch, [self._site("cosmos-alic1", datetime(2023, 5, 1))])

        run_historic(HistoricSelection(network="cosmos"), CONFIG)

        assert self.build_graph.call_count == 2
        for call in self.build_graph.call_args_list:
            selection, _router, window_start, window_end = call.args
            assert selection == [DimensionSelection(network="cosmos", sites=[f"{SITE_URI}/cosmos-alic1"])]
            assert (window_start, window_end) == (datetime(2023, 5, 1), datetime(2024, 3, 10))

    def test_each_year_gets_its_own_metrics_job_name_suffix(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Tests that each year's processor is given the year as a job name suffix, so metrics do not overwrite."""
        build_processor = self._setup(monkeypatch, [self._site("cosmos-alic1", datetime(2023, 5, 1))])

        run_historic(HistoricSelection(network="cosmos"), CONFIG)

        assert [call.kwargs["job_name_suffix"] for call in build_processor.call_args_list] == ["2023", "2024"]

    def test_failed_graph_build_does_not_stop_remaining_years(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Tests that a year whose graph fails to build is reported at the end while later years still run."""
        build_processor = self._setup(monkeypatch, [self._site("cosmos-alic1", datetime(2023, 1, 1))])
        self.build_graph.side_effect = [RuntimeError("boom"), MagicMock()]

        with pytest.raises(RuntimeError, match="2023-01-01 to 2023-12-31"):
            run_historic(HistoricSelection(network="cosmos"), CONFIG)

        assert build_processor.call_count == 1

    def test_site_starting_after_today_is_not_processed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Tests that a site that has not started yet gives no years to process and is not reported as a failure."""
        build_processor = self._setup(monkeypatch, [self._site("cosmos-future", datetime(2025, 1, 1))])

        run_historic(HistoricSelection(network="cosmos"), CONFIG)

        assert self.build_graph.call_count == 0
        assert build_processor.call_count == 0

    def test_sites_requested_are_passed_on_to_the_site_lookup(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Tests that the network and sites from the selection are used to look up the sites to process."""
        self._setup(monkeypatch, [])
        fetch_sites = MagicMock(return_value=[])
        monkeypatch.setattr("dritimeseriesprocessor.app.run._fetch_network_sites", fetch_sites)
        sites = [f"{SITE_URI}/cosmos-alic1"]

        run_historic(HistoricSelection(network="cosmos", sites=sites), CONFIG)

        assert fetch_sites.call_args.args[1:] == ("cosmos", sites)
