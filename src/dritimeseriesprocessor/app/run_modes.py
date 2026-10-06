"""
The ways the processor can be run, one class for each:

- `StandardRun`: process the selected datasets over the requested date range.
- `HistoricRun`: process every dataset for a network's sites over each site's full operating dates.
- `ListSitesRun`: write the IDs of a network's open sites to a JSON file, for Argo Workflows to fan out over.

`StandardRun` and `HistoricRun` only differ in how they plan the date ranges to process, so `ProcessingRun` does the
processing for both, including putting together the graph, storage, readers, writer and metrics for each date range.
"""

import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta

from dritimeseriesprocessor.cli.selection import DimensionSelection, HistoricSelection, ListSitesSelection, Selection
from dritimeseriesprocessor.configuration.app_config import AppConfig
from dritimeseriesprocessor.dag.dataset_dependency_graph import DatasetDependencyGraph
from dritimeseriesprocessor.io_backend.duckdb_connection import create_duckdb_factory
from dritimeseriesprocessor.io_backend.reader import DuckDBParquetReader, RawFileReader
from dritimeseriesprocessor.io_backend.writer import ByteParquetWriter
from dritimeseriesprocessor.metrics.metrics import Metrics
from dritimeseriesprocessor.models.domain_models.site_metadata import SiteMetadata
from dritimeseriesprocessor.models.mappers.api_to_domain import map_site_metadata
from dritimeseriesprocessor.processing.time_series_processor import TimeSeriesProcessor
from dritimeseriesprocessor.routers.data.data_router import S3DataRouter
from dritimeseriesprocessor.routers.metadata.metadata_router import MetadataRouter
from dritimeseriesprocessor.storage.storage_client import S3StorageClient, StorageClient
from dritimeseriesprocessor.utils.time_utils import split_into_calendar_years, to_datetime
from dritimeseriesprocessor.utils.timer import log_duration
from dritimeseriesprocessor.utils.urls import PROGRAMME_URI, SITE_URI

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Chunk:
    """A date range to process for a selection"""

    selection: list[Selection]
    start_date: datetime
    end_date: datetime
    label: str
    job_name_suffix: str | None = None

    def __str__(self) -> str:
        return f"{self.label} ({self.start_date.date()} to {self.end_date.date()})"


class RunMode(ABC):
    """The parent class for a run mode which defines a way of running the processor."""

    def __init__(self, cfg: AppConfig):
        """Initialise the run mode.

        Args:
            cfg: Application configuration.
        """
        self.cfg = cfg
        self.metadata_router = MetadataRouter(cfg.metadata_api_url)

    @abstractmethod
    def run(self) -> None:
        """Carry out the run."""

    def fetch_sites(self, network: str, sites: list[str] | None = None) -> list[SiteMetadata]:
        """Fetch metadata for the given sites, or for every site in the network if none are given.

        A named site whose metadata puts it in a different network is left out. A named site with no network in its
        metadata is kept.

        Args:
            network: The network identifier.
            sites: Site IDs to fetch. If omitted, all sites for the network are fetched.

        Returns:
            Metadata for each site found.
        """
        if not sites:
            return [map_site_metadata(item) for item in self.metadata_router.fetch_sites_by_network(network).items]

        network_uri = f"{PROGRAMME_URI}/{network}"
        found_sites = []
        for item in self.metadata_router.fetch_sites(sites).items:
            site = map_site_metadata(item)
            if site.network is not None and site.network != network_uri:
                logger.warning(f"Site [{site.site_id}] is not in network [{network}], excluding.")
                continue
            found_sites.append(site)
        return found_sites


class ListSitesRun(RunMode):
    """Write the IDs of a network's sites that were open during a date range to a JSON file.

    Argo Workflows captures the file as the step result, to pass to later workflow steps.
    """

    OUTPUT_PATH = "/tmp/sites.json"

    def __init__(self, cfg: AppConfig, selection: ListSitesSelection, start_date: datetime, end_date: datetime):
        """Initialise the run.

        Args:
            cfg: Application configuration.
            selection: The network, and optionally the sites (still checked for network membership), to list.
            start_date: Start of the date range to find open sites for (inclusive).
            end_date: End of the date range to find open sites for (inclusive).
        """
        super().__init__(cfg)
        self.selection = selection
        self.start_date = start_date
        self.end_date = end_date

    def run(self) -> None:
        """List the open sites and write their IDs to `OUTPUT_PATH`."""
        logger.info(
            f"Listing sites: start_date={self.start_date}, end_date={self.end_date}, network={self.selection.network}"
        )
        site_ids = [
            site.site_id.removeprefix(f"{SITE_URI}/")
            for site in self.fetch_sites(self.selection.network, self.selection.sites)
            if site.is_active(self.start_date, self.end_date)
        ]
        logger.info(f"Found [{len(site_ids)}] sites: {site_ids}")

        with open(self.OUTPUT_PATH, "w") as output_file:
            json.dump(site_ids, output_file)


class ProcessingRun(RunMode):
    """A run that processes data, one chunk at a time.

    Each subclass plans its chunks. Each chunk then gets its own dependency graph and processor, so the data it holds
    can be freed before the next one starts.
    """

    def __init__(self, cfg: AppConfig):
        """Initialise the run.

        Args:
            cfg: Application configuration.
        """
        super().__init__(cfg)
        self.failures: list[str] = []

    @abstractmethod
    def plan(self) -> list[Chunk]:
        """Work out the chunks to process."""

    def run(self) -> None:
        """Process each planned chunk in turn."""

        chunks = self.plan()
        logger.info(f"Planned {len(chunks)} chunk(s) to process.")
        for chunk in chunks:
            self._process(chunk)

        if self.failures:
            raise RuntimeError(f"Run had {len(self.failures)} failure(s): {self.failures}")

    def _process(self, chunk: Chunk) -> None:
        """Build a dependency graph and processor for a chunk and run it, recording a failure if anything goes wrong.

        Args:
            chunk: The chunk to process.
        """
        logger.info(f"Processing chunk: {chunk}")
        try:
            graph = self._build_dependency_graph(chunk)
            processor = self._build_processor(graph, chunk)
            processor.run()
        except Exception:
            logger.exception(f"Failed processing chunk: {chunk}")
            self.failures.append(str(chunk))

    @log_duration("Dependency graph build duration: ")
    def _build_dependency_graph(self, chunk: Chunk) -> DatasetDependencyGraph:
        """Build the dataset dependency graph for a chunk. Sites that were not open during it are left out.

        Args:
            chunk: The chunk to build the graph for.

        Returns:
            A DatasetDependencyGraph ready for execution.
        """
        logger.info("Gathering metadata and building dataset dependency graph.")
        graph = DatasetDependencyGraph(
            selection=chunk.selection,
            metadata_router=self.metadata_router,
            start_date=chunk.start_date,
            end_date=chunk.end_date,
        )
        graph.build()
        logger.info(f"Found {len(graph.datasets)} datasets to process.")
        return graph

    def _build_processor(self, graph: DatasetDependencyGraph, chunk: Chunk) -> TimeSeriesProcessor:
        """Build a TimeSeriesProcessor for a chunk around its dependency graph.

        Each processor gets its own data router, because running a processor closes the router's DuckDB connection.

        Args:
            graph: The chunk's dependency graph.
            chunk: The chunk to process.

        Returns:
            A TimeSeriesProcessor ready for running.
        """
        storage = self._build_storage()
        reader = DuckDBParquetReader(create_duckdb_factory())
        raw_reader = RawFileReader(storage)
        writer = ByteParquetWriter(storage)
        data_router = S3DataRouter(reader, raw_reader, storage)

        job_name = self.cfg.pushgateway_job_name
        if chunk.job_name_suffix:
            job_name = f"{job_name}-{chunk.job_name_suffix}"
        site_label = ",".join(sorted(graph.root_site_ids))
        metrics = Metrics(self.cfg.pushgateway_url, job_name, site=site_label)

        return TimeSeriesProcessor(
            graph=graph,
            data_router=data_router,
            data_writer=writer,
            start_date=chunk.start_date,
            end_date=chunk.end_date,
            metrics=metrics,
        )

    def _build_storage(self) -> StorageClient:
        """Construct the storage client used for reading and writing datasets.

        Returns:
            A configured StorageClient instance.
        """
        return S3StorageClient(
            self.cfg.AWS_ACCESS_KEY_ID,
            self.cfg.AWS_SECRET_ACCESS_KEY,
            self.cfg.AWS_DEFAULT_REGION,
            self.cfg.endpoint_url,
        )


class StandardRun(ProcessingRun):
    """Process the selected datasets over the requested date range.

    A date range longer than one year is run one calendar year at a time, to limit memory use and data
    load times. Shorter ranges are run in one go.

    For selections made by site, the start date is moved forward to when the first of the selected sites opened, and
    each year only includes the selections with a site open during it.
    """

    def __init__(self, cfg: AppConfig, selection: list[Selection], start_date: datetime, end_date: datetime):
        """Initialise the run.

        Args:
            cfg: Application configuration.
            selection: Selection specification for which datasets should be processed.
            start_date: Start of the date range to process (inclusive).
            end_date: End of the date range to process (inclusive).
        """
        super().__init__(cfg)
        self.selection = selection
        self.start_date = start_date
        self.end_date = end_date

    def plan(self) -> list[Chunk]:
        """Work out the date ranges to process, and which selections to include in each.

        Returns:
            The chunks to process, oldest first.

        Raises:
            RuntimeError: If a selection made by site has no site open during the date range.
        """
        selection_sites = [self._fetch_selection_sites(item) for item in self.selection]
        if not all(self._any_open(sites, self.start_date, self.end_date) for _, sites in selection_sites):
            raise RuntimeError("no active sites found during requested processing window")

        # Gather the sites of every selection made by site, to find when the first of them opened
        all_sites: list[SiteMetadata] = []
        for _, sites in selection_sites:
            if sites is not None:
                all_sites.extend(sites)

        start_date = self._clamp_start_to_sites(all_sites)
        date_ranges = self._split_date_range(start_date, self.end_date)
        label = ", ".join(str(item) for item in self.selection)

        chunks = []
        for range_start, range_end in date_ranges:
            range_selection = [item for item, sites in selection_sites if self._any_open(sites, range_start, range_end)]
            if not range_selection:
                logger.info(f"Skipping {range_start.date()} to {range_end.date()}: no selected site was open")
                continue

            job_name_suffix = str(range_start.year) if len(date_ranges) > 1 else None
            chunks.append(Chunk(range_selection, range_start, range_end, label, job_name_suffix))
        return chunks

    def _fetch_selection_sites(self, item: Selection) -> tuple[Selection, list[SiteMetadata] | None]:
        """Fetch the site metadata for a selection made by site.

        Args:
            item: One of the selections to process.

        Returns:
            The selection, and its sites' metadata. Selections not made by site are returned as they are, with None for
            the sites
        """
        if not isinstance(item, DimensionSelection):
            # A DimensionSelection doesn't include site selection
            return item, None

        sites = self.fetch_sites(item.network, item.sites)
        found_site_ids = {site.site_id for site in sites}
        if item.sites and not found_site_ids.issuperset(item.sites):
            item = replace(item, sites=[site_id for site_id in item.sites if site_id in found_site_ids])
        return item, sites

    def _clamp_start_to_sites(self, sites: list[SiteMetadata]) -> datetime:
        """Clamp start date to latest of: (a) the given start date, or (b) the day the first of the given sites opened.

        Args:
            sites: Metadata for the selected sites.

        Returns:
            The start date to use.
        """
        open_sites = [site for site in sites if site.is_active(self.start_date, self.end_date)]
        site_starts = [site.start_date for site in open_sites]
        if not open_sites or None in site_starts:
            return self.start_date

        first_opened = min(site_start for site_start in site_starts if site_start is not None)
        return max(self.start_date, to_datetime(first_opened.date()))

    @classmethod
    def _split_date_range(cls, start_date: datetime, end_date: datetime) -> list[tuple[datetime, datetime]]:
        """Split a date range into calendar years if it is longer than one full year, otherwise leave it whole.

        Args:
            start_date: Start of the date range (inclusive).
            end_date: End of the date range (inclusive).

        Returns:
            The (start, end) date ranges to process, oldest first.
        """
        if end_date - start_date > timedelta(days=365):
            return split_into_calendar_years(start_date, end_date)
        return [(start_date, end_date)]

    @staticmethod
    def _any_open(sites: list[SiteMetadata] | None, start_date: datetime, end_date: datetime) -> bool:
        """Return whether any of the sites were open during the date range, or True if the sites aren't known.

        Args:
            sites: Metadata for the sites, or None if they aren't known.
            start_date: Start of the date range (inclusive).
            end_date: End of the date range (inclusive).

        Returns:
            True if any of the sites were open during the range, or the sites aren't known.
        """
        return sites is None or any(site.is_active(start_date, end_date) for site in sites)


class HistoricRun(ProcessingRun):
    """Process every dataset for a network's sites over each site's full operating dates, one calendar year at a time.

    A site runs from its start date in the metadata to its end date, or to today if it is still open. A site with no
    start date is skipped and reported as a failure.
    """

    def __init__(self, cfg: AppConfig, selection: HistoricSelection):
        """Initialise the run.

        Args:
            cfg: Application configuration.
            selection: The network, and optionally the sites, to process.
        """
        super().__init__(cfg)
        self.selection = selection

    def plan(self) -> list[Chunk]:
        """Work out the calendar years to process for each site.

        Returns:
            The chunks to process, site by site and oldest first.
        """
        today = date.today()
        chunks = []
        for site in self.fetch_sites(self.selection.network, self.selection.sites):
            site_name = site.site_id.removeprefix(f"{SITE_URI}/")
            if site.start_date is None:
                logger.error(f"Site [{site_name}] has no start date in its metadata, skipping.")
                self.failures.append(f"{site_name} (no start date)")
                continue

            site_end = min(site.end_date.date(), today) if site.end_date else today
            site_selection: list[Selection] = [DimensionSelection(network=self.selection.network, sites=[site.site_id])]
            chunks += [
                Chunk(site_selection, year_start, year_end, site_name, job_name_suffix=str(year_start.year))
                for year_start, year_end in split_into_calendar_years(site.start_date, site_end)
                if site.is_active(year_start, year_end)
            ]
        return chunks
