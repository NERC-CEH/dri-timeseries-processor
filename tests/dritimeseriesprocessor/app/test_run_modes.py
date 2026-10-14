import json
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from freezegun import freeze_time

from dritimeseriesprocessor.app import run_modes
from dritimeseriesprocessor.app.run_modes import Chunk, HistoricRun, ListSitesRun, ProcessingRun, StandardRun
from dritimeseriesprocessor.cli.selection import (
    DatasetIdSelection,
    DimensionSelection,
    HistoricSelection,
    ListSitesSelection,
    Selection,
)
from dritimeseriesprocessor.models.domain_models.site_metadata import SiteMetadata
from dritimeseriesprocessor.utils.urls import PROGRAMME_URI, SITE_URI

CONFIG = MagicMock(metadata_api_url="http://fake-api", pushgateway_url="http://gateway", pushgateway_job_name="a-job")
START = datetime(2024, 1, 1)
END = datetime(2024, 1, 31)


def make_site(
    name: str,
    start: datetime | None = None,
    end: datetime | None = None,
    network: str | None = f"{PROGRAMME_URI}/cosmos",
) -> SiteMetadata:
    """Create metadata for a site with the given operating dates."""
    return SiteMetadata(site_id=f"{SITE_URI}/{name}", network=network, start_date=start, end_date=end)


def site_uris(*names: str) -> list[str]:
    """Return the full site URIs for the given site names."""
    return [f"{SITE_URI}/{name}" for name in names]


def fake_fetch_sites(sites: list[SiteMetadata]) -> MagicMock:
    """Create a stand-in for `RunMode.fetch_sites` that returns `sites`, or only the named ones if sites are named."""
    return MagicMock(
        side_effect=lambda _network, named_sites=None: [
            site for site in sites if not named_sites or site.site_id in named_sites
        ]
    )


class FixedPlanRun(ProcessingRun):
    """A processing run with a fixed plan, for testing the processing shared by all processing runs."""

    def __init__(self, chunks: list[Chunk]):
        super().__init__(CONFIG)
        self.chunks = chunks

    def plan(self) -> list[Chunk]:
        return self.chunks


class TestChunk:
    def test_chunk_is_described_by_its_label_and_dates(self) -> None:
        """Tests that a chunk is described by its label followed by its first and last days."""
        chunk = Chunk([], datetime(2023, 1, 1), datetime(2023, 12, 31), "cosmos-alic1")

        assert str(chunk) == "cosmos-alic1 (2023-01-01 to 2023-12-31)"


class TestFetchSites:
    @pytest.fixture
    def router(self) -> MagicMock:
        """A fake metadata router."""
        return MagicMock()

    @pytest.fixture
    def run(self, monkeypatch: pytest.MonkeyPatch, router: MagicMock) -> ListSitesRun:
        """A run mode using the fake router, which returns SiteMetadata directly so no mapping is needed."""
        monkeypatch.setattr(run_modes, "map_site_metadata", lambda item: item)
        run = ListSitesRun(CONFIG, ListSitesSelection(network="cosmos"), START, END)
        run.metadata_router = router
        return run

    def test_every_network_site_is_fetched_when_none_are_named(self, run: ListSitesRun, router: MagicMock) -> None:
        """Tests that every site in the network is fetched, without a network check, when no sites are named."""
        sites = [make_site("cosmos-alic1"), make_site("nmdb-jung", network=f"{PROGRAMME_URI}/nmdb")]
        router.fetch_sites_by_network.return_value.items = sites

        assert run.fetch_sites("cosmos") == sites
        router.fetch_sites_by_network.assert_called_once_with("cosmos")
        router.fetch_sites.assert_not_called()

    def test_named_sites_are_fetched_by_id(self, run: ListSitesRun, router: MagicMock) -> None:
        """Tests that named sites are fetched by their IDs."""
        router.fetch_sites.return_value.items = [make_site("cosmos-alic1")]

        assert run.fetch_sites("cosmos", site_uris("cosmos-alic1")) == [make_site("cosmos-alic1")]
        router.fetch_sites.assert_called_once_with(site_uris("cosmos-alic1"))
        router.fetch_sites_by_network.assert_not_called()

    def test_named_site_from_another_network_is_left_out(self, run: ListSitesRun, router: MagicMock) -> None:
        """Tests that a named site whose metadata puts it in a different network is left out."""
        router.fetch_sites.return_value.items = [
            make_site("cosmos-alic1"),
            make_site("nmdb-jung", network=f"{PROGRAMME_URI}/nmdb"),
        ]

        assert run.fetch_sites("cosmos", site_uris("cosmos-alic1", "nmdb-jung")) == [make_site("cosmos-alic1")]

    def test_named_site_with_no_network_is_kept(self, run: ListSitesRun, router: MagicMock) -> None:
        """Tests that a named site with no network in its metadata is kept."""
        router.fetch_sites.return_value.items = [make_site("flux-plynl", network=None)]

        assert run.fetch_sites("fdri", site_uris("flux-plynl")) == [make_site("flux-plynl", network=None)]


class TestListSitesRun:
    @pytest.fixture
    def output_path(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
        """Write the site list to a temporary file rather than `/tmp/sites.json`."""
        output_path = tmp_path / "sites.json"
        monkeypatch.setattr(ListSitesRun, "OUTPUT_PATH", str(output_path))
        return output_path

    def _run(
        self,
        sites: list[SiteMetadata],
        selection: ListSitesSelection | None = None,
        start_date: datetime | None = START,
        end_date: datetime | None = END,
    ) -> MagicMock:
        """Run list-sites (for January 2024 by default) against the given site metadata, and return the site lookup
        used."""
        run = ListSitesRun(CONFIG, selection or ListSitesSelection(network="cosmos"), start_date, end_date)
        fetch_sites = fake_fetch_sites(sites)
        run.fetch_sites = fetch_sites
        run.run()
        return fetch_sites

    def test_writes_ids_of_open_sites(self, output_path: Path) -> None:
        """Tests that the IDs of the open sites are written to the file, without the site URI prefix."""
        self._run([make_site("cosmos-alic1", datetime(2000, 1, 1)), make_site("cosmos-bunny", datetime(2000, 1, 1))])

        assert json.loads(output_path.read_text()) == ["cosmos-alic1", "cosmos-bunny"]

    def test_sites_not_open_during_the_dates_are_left_out(self, output_path: Path) -> None:
        """Tests that sites that closed before, or opened after, the date range are left out."""
        self._run(
            [
                make_site("cosmos-closed", datetime(2000, 1, 1), datetime(2023, 6, 1)),
                make_site("cosmos-alic1", datetime(2000, 1, 1)),
                make_site("cosmos-future", datetime(2024, 2, 1)),
            ]
        )

        assert json.loads(output_path.read_text()) == ["cosmos-alic1"]

    def test_site_that_opened_on_the_last_day_is_listed(self, output_path: Path) -> None:
        """Tests that a site that opened part way through the last day of the range is listed."""
        self._run([make_site("cosmos-alic1", datetime(2024, 1, 31, 10, 30))])

        assert json.loads(output_path.read_text()) == ["cosmos-alic1"]

    def test_no_dates_lists_every_site(self, output_path: Path) -> None:
        """Tests that with no dates, every site is listed, including ones that have closed or not yet opened."""
        self._run(
            [
                make_site("cosmos-closed", datetime(2000, 1, 1), datetime(2023, 6, 1)),
                make_site("cosmos-alic1", datetime(2000, 1, 1)),
                make_site("cosmos-future", datetime(2099, 1, 1)),
                make_site("cosmos-undated"),
            ],
            start_date=None,
            end_date=None,
        )

        assert json.loads(output_path.read_text()) == [
            "cosmos-closed",
            "cosmos-alic1",
            "cosmos-future",
            "cosmos-undated",
        ]

    def test_no_sites_writes_an_empty_list(self, output_path: Path) -> None:
        """Tests that a network with no sites writes an empty list."""
        self._run([])

        assert json.loads(output_path.read_text()) == []

    def test_sites_are_looked_up_with_the_selection_network_and_sites(self, output_path: Path) -> None:
        """Tests that sites are looked up using the network and sites of the selection."""
        fetch_sites = self._run([], ListSitesSelection(network="cosmos", sites=site_uris("cosmos-alic1")))

        fetch_sites.assert_called_once_with("cosmos", site_uris("cosmos-alic1"))


class TestProcessingRun:
    @staticmethod
    def _chunk(year: int, label: str = "a-label") -> Chunk:
        """Create a chunk covering one calendar year."""
        return Chunk([DimensionSelection(network="cosmos")], datetime(year, 1, 1), datetime(year, 12, 31), label)

    @staticmethod
    def _patch_builders(run: ProcessingRun) -> tuple[MagicMock, MagicMock]:
        """Replace the graph and processor builders on a run with mocks, and return them."""
        build_graph = MagicMock()
        build_processor = MagicMock()
        run._build_dependency_graph = build_graph
        run._build_processor = build_processor
        return build_graph, build_processor

    def test_each_chunk_is_built_and_run_in_turn(self) -> None:
        """Tests that each chunk gets its own graph and processor, which are built and run in order."""
        chunks = [self._chunk(2022), self._chunk(2023)]
        run = FixedPlanRun(chunks)
        build_graph, build_processor = self._patch_builders(run)

        run.run()

        assert [call.args[0] for call in build_graph.call_args_list] == chunks
        assert [call.args for call in build_processor.call_args_list] == [
            (build_graph.return_value, chunk) for chunk in chunks
        ]
        assert build_processor.return_value.run.call_count == 2

    def test_failed_chunk_is_reported_after_the_others_have_run(self) -> None:
        """Tests that a chunk that fails does not stop later chunks, and is reported once they have all run."""
        run = FixedPlanRun([self._chunk(2022), self._chunk(2023)])
        _, build_processor = self._patch_builders(run)
        build_processor.return_value.run.side_effect = [RuntimeError("boom"), None]

        with pytest.raises(RuntimeError, match=r"Run had 1 failure\(s\): \['a-label \(2022-01-01 to 2022-12-31\)'\]"):
            run.run()

        assert build_processor.return_value.run.call_count == 2

    def test_failed_graph_build_is_reported_after_the_others_have_run(self) -> None:
        """Tests that a chunk whose graph fails to build is reported, and later chunks still run."""
        run = FixedPlanRun([self._chunk(2022), self._chunk(2023)])
        build_graph, build_processor = self._patch_builders(run)
        build_graph.side_effect = [RuntimeError("boom"), MagicMock()]

        with pytest.raises(RuntimeError, match=r"2022-01-01 to 2022-12-31"):
            run.run()

        assert build_processor.call_count == 1

    def test_failures_found_while_planning_are_reported(self) -> None:
        """Tests that failures recorded while planning are reported at the end, after the chunks have run."""
        run = FixedPlanRun([self._chunk(2023)])
        _, build_processor = self._patch_builders(run)
        run.failures.append("a-site (no start date)")

        with pytest.raises(RuntimeError, match=r"a-site \(no start date\)"):
            run.run()

        build_processor.return_value.run.assert_called_once_with()

    def test_graph_is_built_for_the_chunk_selection_and_dates(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Tests that the dependency graph is created with the chunk's selection and dates, and then built."""
        graph_class = MagicMock()
        monkeypatch.setattr(run_modes, "DatasetDependencyGraph", graph_class)
        run = FixedPlanRun([])
        chunk = self._chunk(2023)

        graph = run._build_dependency_graph(chunk)

        graph_class.assert_called_once_with(
            selection=chunk.selection,
            metadata_router=run.metadata_router,
            start_date=datetime(2023, 1, 1),
            end_date=datetime(2023, 12, 31),
        )
        graph_class.return_value.build.assert_called_once_with()
        assert graph is graph_class.return_value

    @pytest.mark.parametrize(
        "job_name_suffix, expected_job_name", [(None, "a-job"), ("2023", "a-job-2023")], ids=["no_suffix", "suffix"]
    )
    def test_processor_metrics_use_the_job_name_and_site_label(
        self, monkeypatch: pytest.MonkeyPatch, job_name_suffix: str | None, expected_job_name: str
    ) -> None:
        """Tests that the processor's metrics use the job name, plus any suffix, and the graph's sites in order."""
        for name in [
            "S3StorageClient",
            "create_duckdb_factory",
            "DuckDBParquetReader",
            "RawFileReader",
            "ByteParquetWriter",
            "S3DataRouter",
            "TimeSeriesProcessor",
        ]:
            monkeypatch.setattr(run_modes, name, MagicMock())
        metrics = MagicMock()
        monkeypatch.setattr(run_modes, "Metrics", metrics)
        chunk = Chunk([], datetime(2023, 1, 1), datetime(2023, 12, 31), "a-label", job_name_suffix)

        FixedPlanRun([])._build_processor(MagicMock(root_site_ids=["site-b", "site-a"]), chunk)

        metrics.assert_called_once_with("http://gateway", expected_job_name, site="site-a,site-b")

    def test_processor_covers_the_chunk_dates(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Tests that the processor is built for the chunk's graph and dates."""
        for name in [
            "S3StorageClient",
            "create_duckdb_factory",
            "DuckDBParquetReader",
            "RawFileReader",
            "ByteParquetWriter",
            "S3DataRouter",
            "Metrics",
        ]:
            monkeypatch.setattr(run_modes, name, MagicMock())
        processor_class = MagicMock()
        monkeypatch.setattr(run_modes, "TimeSeriesProcessor", processor_class)
        graph = MagicMock(root_site_ids=[])

        FixedPlanRun([])._build_processor(graph, self._chunk(2023))

        call_kwargs = processor_class.call_args.kwargs
        assert (call_kwargs["graph"], call_kwargs["start_date"], call_kwargs["end_date"]) == (
            graph,
            datetime(2023, 1, 1),
            datetime(2023, 12, 31),
        )


class TestStandardRunPlan:
    @staticmethod
    def _plan(
        selection: list[Selection], start: datetime, end: datetime, sites: list[SiteMetadata] | None = None
    ) -> tuple[MagicMock, list[Chunk]]:
        """Plan a standard run against the given site metadata, and return the site lookup used and the chunks."""
        run = StandardRun(CONFIG, selection, start, end)
        fetch_sites = fake_fetch_sites(sites or [])
        run.fetch_sites = fetch_sites
        return fetch_sites, run.plan()

    @staticmethod
    def _windows(chunks: list[Chunk]) -> list[tuple[datetime, datetime]]:
        """Return the (start, end) dates of each chunk."""
        return [(chunk.start_date, chunk.end_date) for chunk in chunks]

    def test_short_range_is_one_chunk_as_requested(self) -> None:
        """Tests that a short range is one chunk over the dates asked for, labelled by the selection, with no suffix."""
        selection: list[Selection] = [DimensionSelection(network="cosmos")]

        _, chunks = self._plan(selection, START, END, [make_site("cosmos-alic1", datetime(2000, 1, 1))])

        assert chunks == [Chunk(selection, START, END, str(selection[0]), None)]

    def test_short_range_across_new_year_is_not_split(self) -> None:
        """Tests that a short range that crosses New Year is still one chunk."""
        _, chunks = self._plan(
            [DimensionSelection(network="cosmos")],
            datetime(2023, 12, 30),
            datetime(2024, 1, 2),
            [make_site("cosmos-alic1", datetime(2000, 1, 1))],
        )

        assert self._windows(chunks) == [(datetime(2023, 12, 30), datetime(2024, 1, 2))]

    def test_range_of_365_days_is_not_split(self) -> None:
        """Tests that a range whose end is 365 days after its start is left whole."""
        selection: list[Selection] = [DatasetIdSelection(dataset_ids=["a-dataset"])]

        _, chunks = self._plan(selection, datetime(2023, 1, 1), datetime(2024, 1, 1))

        assert self._windows(chunks) == [(datetime(2023, 1, 1), datetime(2024, 1, 1))]

    def test_range_of_366_days_is_split_by_calendar_year(self) -> None:
        """Tests that a range whose end is 366 days after its start is split by calendar year."""
        selection: list[Selection] = [DatasetIdSelection(dataset_ids=["a-dataset"])]

        _, chunks = self._plan(selection, datetime(2023, 1, 1), datetime(2024, 1, 2))

        assert self._windows(chunks) == [
            (datetime(2023, 1, 1), datetime(2023, 12, 31)),
            (datetime(2024, 1, 1), datetime(2024, 1, 2)),
        ]

    def test_long_range_is_split_into_calendar_years_with_year_suffix(self) -> None:
        """Tests that a range longer than a year is one chunk per calendar year, each with its year as job suffix."""
        _, chunks = self._plan(
            [DimensionSelection(network="cosmos")],
            datetime(2022, 6, 1),
            datetime(2024, 2, 1),
            [make_site("cosmos-alic1", datetime(2000, 1, 1))],
        )

        assert self._windows(chunks) == [
            (datetime(2022, 6, 1), datetime(2022, 12, 31)),
            (datetime(2023, 1, 1), datetime(2023, 12, 31)),
            (datetime(2024, 1, 1), datetime(2024, 2, 1)),
        ]
        assert [chunk.job_name_suffix for chunk in chunks] == ["2022", "2023", "2024"]

    def test_years_before_the_site_opened_are_not_planned(self) -> None:
        """Tests that a long range starting years before the site opened starts on the day the site opened."""
        _, chunks = self._plan(
            [DimensionSelection(network="cosmos")],
            datetime(2013, 1, 1),
            datetime(2018, 2, 1),
            [make_site("cosmos-alic1", datetime(2016, 3, 1))],
        )

        assert self._windows(chunks) == [
            (datetime(2016, 3, 1), datetime(2016, 12, 31)),
            (datetime(2017, 1, 1), datetime(2017, 12, 31)),
            (datetime(2018, 1, 1), datetime(2018, 2, 1)),
        ]

    def test_short_range_starts_on_the_day_the_site_opened(self) -> None:
        """Tests that a short range starting before the site opened starts on the day it opened, at midnight."""
        _, chunks = self._plan(
            [DimensionSelection(network="cosmos")],
            datetime(2023, 1, 1),
            datetime(2023, 12, 31),
            [make_site("cosmos-alic1", datetime(2023, 6, 15, 10, 30))],
        )

        assert self._windows(chunks) == [(datetime(2023, 6, 15), datetime(2023, 12, 31))]

    def test_site_that_opened_on_the_last_day_is_included(self) -> None:
        """Tests that a site that opened part way through the last day of the range is still planned."""
        _, chunks = self._plan(
            [DimensionSelection(network="cosmos")],
            START,
            END,
            [make_site("cosmos-alic1", datetime(2024, 1, 31, 10, 30))],
        )

        assert self._windows(chunks) == [(END, END)]

    def test_end_date_is_not_moved_for_a_closed_site(self) -> None:
        """Tests that the end date is left as asked for when the site closed before it, as only the start is moved."""
        _, chunks = self._plan(
            [DimensionSelection(network="cosmos")],
            START,
            datetime(2024, 3, 1),
            [make_site("cosmos-alic1", datetime(2000, 1, 1), datetime(2024, 1, 10, 9, 0))],
        )

        assert self._windows(chunks) == [(START, datetime(2024, 3, 1))]

    def test_site_with_no_start_date_keeps_the_requested_start(self) -> None:
        """Tests that a site with no start date in its metadata is planned over the dates asked for."""
        _, chunks = self._plan([DimensionSelection(network="cosmos")], START, END, [make_site("cosmos-alic1", None)])

        assert self._windows(chunks) == [(START, END)]

    def test_several_sites_share_each_year_from_when_the_first_opened(self) -> None:
        """Tests that a selection of several sites is planned as one per year, starting when the first opened."""
        selection: list[Selection] = [DimensionSelection(network="cosmos", variables=["TA"], periodicities=["P1D"])]

        _, chunks = self._plan(
            selection,
            datetime(2020, 1, 1),
            datetime(2023, 6, 30),
            [make_site("cosmos-alic1", datetime(2022, 3, 1)), make_site("cosmos-bunny", datetime(2023, 1, 1))],
        )

        assert self._windows(chunks) == [
            (datetime(2022, 3, 1), datetime(2022, 12, 31)),
            (datetime(2023, 1, 1), datetime(2023, 6, 30)),
        ]
        assert [chunk.selection for chunk in chunks] == [selection, selection]

    def test_selection_is_left_out_of_years_its_site_was_not_open(self) -> None:
        """Tests that each selection made by site is only included in the years its site was open."""
        alic1, bunny = [
            DimensionSelection(network="cosmos", sites=site_uris(name), variables=["TA"], periodicities=["PT30M"])
            for name in ["cosmos-alic1", "cosmos-bunny"]
        ]

        _, chunks = self._plan(
            [alic1, bunny],
            datetime(2022, 1, 1),
            datetime(2023, 12, 31),
            [make_site("cosmos-alic1", datetime(2000, 1, 1)), make_site("cosmos-bunny", datetime(2023, 6, 1))],
        )

        assert [chunk.selection for chunk in chunks] == [[alic1], [alic1, bunny]]

    def test_year_with_no_open_site_is_skipped(self) -> None:
        """Tests that a year in which none of the selected sites were open is skipped."""
        _, chunks = self._plan(
            [DimensionSelection(network="cosmos")],
            datetime(2018, 1, 1),
            datetime(2021, 12, 31),
            [
                make_site("cosmos-alic1", datetime(2015, 1, 1), datetime(2019, 1, 1)),
                make_site("cosmos-bunny", datetime(2020, 6, 1)),
            ],
        )

        assert [chunk.start_date.year for chunk in chunks] == [2018, 2020, 2021]

    def test_dataset_selection_is_split_by_year_without_looking_up_sites(self) -> None:
        """Tests that a dataset ID selection is split by year over the dates asked for, without looking up sites."""
        selection: list[Selection] = [DatasetIdSelection(dataset_ids=["a-dataset"])]

        fetch_sites, chunks = self._plan(selection, datetime(2022, 6, 1), datetime(2024, 2, 1))

        fetch_sites.assert_not_called()
        assert [chunk.selection for chunk in chunks] == [selection, selection, selection]
        assert self._windows(chunks)[0] == (datetime(2022, 6, 1), datetime(2022, 12, 31))

    def test_sites_are_looked_up_with_the_selection_network_and_sites(self) -> None:
        """Tests that sites are looked up using the network and sites of the selection."""
        fetch_sites, _ = self._plan(
            [DimensionSelection(network="cosmos", sites=site_uris("cosmos-alic1"))],
            START,
            END,
            [make_site("cosmos-alic1", datetime(2000, 1, 1))],
        )

        fetch_sites.assert_called_once_with("cosmos", site_uris("cosmos-alic1"))

    def test_sites_left_out_by_the_lookup_are_taken_out_of_the_selection(self) -> None:
        """Tests that named sites the lookup leaves out are taken out of the selection given to the graph."""
        selection = DimensionSelection(network="cosmos", sites=site_uris("cosmos-alic1", "nmdb-jung"), variables=["TA"])

        _, chunks = self._plan([selection], START, END, [make_site("cosmos-alic1", datetime(2000, 1, 1))])

        assert chunks[0].selection == [
            DimensionSelection(network="cosmos", sites=site_uris("cosmos-alic1"), variables=["TA"])
        ]

    def test_selection_is_unchanged_when_no_sites_are_left_out(self) -> None:
        """Tests that a selection is passed on as it is when the lookup finds all of its named sites."""
        selection = DimensionSelection(network="cosmos", sites=site_uris("cosmos-alic1"))

        _, chunks = self._plan([selection], START, END, [make_site("cosmos-alic1", datetime(2000, 1, 1))])

        assert chunks[0].selection[0] is selection

    def test_no_open_sites_raises_an_error(self) -> None:
        """Tests that an error is raised if no sites were open during the date range."""
        with pytest.raises(RuntimeError, match="no active sites found"):
            self._plan(
                [DimensionSelection(network="cosmos")],
                START,
                END,
                [make_site("cosmos-closed", datetime(2000, 1, 1), datetime(2023, 1, 1))],
            )

    def test_any_selection_without_an_open_site_raises_an_error(self) -> None:
        """Tests that planning fails if any one selection made by site has no site open during the date range."""
        selection: list[Selection] = [
            DimensionSelection(network="cosmos", sites=site_uris(name)) for name in ["cosmos-alic1", "cosmos-closed"]
        ]

        with pytest.raises(RuntimeError, match="no active sites found"):
            self._plan(
                selection,
                START,
                END,
                [
                    make_site("cosmos-alic1", datetime(2000, 1, 1)),
                    make_site("cosmos-closed", datetime(2000, 1, 1), datetime(2023, 1, 1)),
                ],
            )

    def test_selection_whose_named_sites_are_all_left_out_raises_an_error(self) -> None:
        """Tests that planning fails if the lookup leaves out every named site in a selection."""
        with pytest.raises(RuntimeError, match="no active sites found"):
            self._plan([DimensionSelection(network="cosmos", sites=site_uris("nmdb-jung"))], START, END, [])


class TestClampStartToSites:
    @staticmethod
    def _clamp(start: datetime, end: datetime, sites: list[SiteMetadata]) -> datetime:
        """Return the start date a standard run over the given dates would use for the given sites."""
        return StandardRun(CONFIG, [], start, end)._clamp_start_to_sites(sites)

    def test_start_moves_forward_to_the_day_the_first_site_opened(self) -> None:
        """Tests that the start moves forward to the day the earliest site opened, ignoring the time of day."""
        sites = [make_site("a-site", datetime(2023, 9, 1)), make_site("b-site", datetime(2023, 6, 15, 10, 30))]

        assert self._clamp(datetime(2020, 1, 1), datetime(2024, 1, 1), sites) == datetime(2023, 6, 15)

    def test_start_is_not_moved_back_when_sites_opened_earlier(self) -> None:
        """Tests that the start is left alone when the sites opened before it."""
        assert self._clamp(START, END, [make_site("a-site", datetime(2000, 1, 1))]) == START

    def test_sites_closed_before_the_range_are_ignored(self) -> None:
        """Tests that a site that closed before the range does not hold the start back."""
        sites = [
            make_site("old-site", datetime(2000, 1, 1), datetime(2005, 1, 1)),
            make_site("new-site", datetime(2023, 6, 1)),
        ]

        assert self._clamp(datetime(2020, 1, 1), datetime(2024, 1, 1), sites) == datetime(2023, 6, 1)

    def test_open_site_with_no_start_date_leaves_the_start_alone(self) -> None:
        """Tests that the start is not moved if any open site has no start date in its metadata."""
        sites = [make_site("a-site", None), make_site("b-site", datetime(2023, 6, 1))]

        assert self._clamp(datetime(2020, 1, 1), datetime(2024, 1, 1), sites) == datetime(2020, 1, 1)

    def test_no_sites_leaves_the_start_alone(self) -> None:
        """Tests that the start is not moved when there are no sites."""
        assert self._clamp(START, END, []) == START


@freeze_time("2024-03-10")
class TestHistoricRunPlan:
    @staticmethod
    def _plan(
        sites: list[SiteMetadata], selection: HistoricSelection | None = None
    ) -> tuple[list[Chunk], list[str], MagicMock]:
        """Plan a historic run against the given site metadata, and return the chunks, failures and site lookup."""
        run = HistoricRun(CONFIG, selection or HistoricSelection(network="cosmos"))
        fetch_sites = fake_fetch_sites(sites)
        run.fetch_sites = fetch_sites
        return run.plan(), run.failures, fetch_sites

    @staticmethod
    def _windows(chunks: list[Chunk]) -> list[tuple[datetime, datetime]]:
        """Return the (start, end) dates of each chunk."""
        return [(chunk.start_date, chunk.end_date) for chunk in chunks]

    def test_open_site_is_planned_one_year_at_a_time_up_to_today(self) -> None:
        """Tests that a site with no end date gets one chunk per year from when it opened up to today."""
        chunks, _, _ = self._plan([make_site("cosmos-alic1", datetime(2022, 7, 1))])

        assert self._windows(chunks) == [
            (datetime(2022, 7, 1), datetime(2022, 12, 31)),
            (datetime(2023, 1, 1), datetime(2023, 12, 31)),
            (datetime(2024, 1, 1), datetime(2024, 3, 10)),
        ]

    def test_each_chunk_selects_just_that_site_labelled_by_name(self) -> None:
        """Tests that each chunk selects only its site, is labelled with the site name and has its year as suffix."""
        chunks, _, _ = self._plan([make_site("cosmos-alic1", datetime(2023, 5, 1))])

        site_selection = [DimensionSelection(network="cosmos", sites=site_uris("cosmos-alic1"))]
        assert [(chunk.selection, chunk.label, chunk.job_name_suffix) for chunk in chunks] == [
            (site_selection, "cosmos-alic1", "2023"),
            (site_selection, "cosmos-alic1", "2024"),
        ]

    def test_closed_site_stops_at_its_end_date(self) -> None:
        """Tests that a closed site is only planned up to its end date."""
        chunks, _, _ = self._plan([make_site("cosmos-alic1", datetime(2020, 1, 1), datetime(2021, 5, 1))])

        assert self._windows(chunks) == [
            (datetime(2020, 1, 1), datetime(2020, 12, 31)),
            (datetime(2021, 1, 1), datetime(2021, 5, 1)),
        ]

    def test_site_with_no_start_date_is_skipped_and_recorded_as_a_failure(self) -> None:
        """Tests that a site with no start date gets no chunks and is recorded as a failure, and others still are."""
        chunks, failures, _ = self._plan(
            [make_site("cosmos-nostart", None), make_site("cosmos-alic1", datetime(2024, 1, 1))]
        )

        assert [chunk.label for chunk in chunks] == ["cosmos-alic1"]
        assert failures == ["cosmos-nostart (no start date)"]

    def test_site_that_opened_on_the_last_day_of_a_year_has_that_day_planned(self) -> None:
        """Tests that a site that opened part way through 31 December still has that day planned."""
        chunks, _, _ = self._plan([make_site("cosmos-alic1", datetime(2023, 12, 31, 10, 30))])

        assert self._windows(chunks) == [
            (datetime(2023, 12, 31), datetime(2023, 12, 31)),
            (datetime(2024, 1, 1), datetime(2024, 3, 10)),
        ]

    def test_year_the_site_closed_at_the_very_start_of_is_skipped(self) -> None:
        """Tests that a site that closed at midnight on 1 January is not planned for that year."""
        chunks, _, _ = self._plan([make_site("cosmos-alic1", datetime(2020, 1, 1), datetime(2021, 1, 1))])

        assert self._windows(chunks) == [(datetime(2020, 1, 1), datetime(2020, 12, 31))]

    def test_site_opening_after_today_is_not_planned(self) -> None:
        """Tests that a site that has not opened yet gets no chunks and is not recorded as a failure."""
        chunks, failures, _ = self._plan([make_site("cosmos-future", datetime(2025, 1, 1))])

        assert chunks == []
        assert failures == []

    def test_sites_are_looked_up_with_the_selection_network_and_sites(self) -> None:
        """Tests that sites are looked up using the network and sites of the selection."""
        _, _, fetch_sites = self._plan([], HistoricSelection(network="cosmos", sites=site_uris("cosmos-alic1")))

        fetch_sites.assert_called_once_with("cosmos", site_uris("cosmos-alic1"))
