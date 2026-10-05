"""
Runtime execution entry points for the time-series processor.

This module is responsible for constructing and running a fully-configured TimeSeriesProcessor. It wires together all
required infrastructure components, including:

- metadata access
- dataset discovery and dependency resolution
- data IO backends (DuckDB readers, parquet writers)
- storage clients
- processing orchestration
"""

import json
import logging
from datetime import datetime

from dritimeseriesprocessor.cli.selection import (
    DimensionSelection,
    HistoricSelection,
    ListSitesSelection,
    RunConfig,
    Selection,
)
from dritimeseriesprocessor.configuration.app_config import AppConfig, app_config
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
from dritimeseriesprocessor.utils.enums import CliSelectionMode
from dritimeseriesprocessor.utils.time_utils import split_into_calendar_years
from dritimeseriesprocessor.utils.timer import log_duration
from dritimeseriesprocessor.utils.urls import PROGRAMME_URI, SITE_URI

logger = logging.getLogger(__name__)


@log_duration("Total time taken: ")
def run_from_config(run_config: RunConfig) -> None:
    """Execute a processing run from a valid RunConfig made of user args.

    Resolve the dataset selection defined in the RunConfig, construct a fully-configured
    TimeSeriesProcessor, and trigger execution of the processing workflow.

    Args:
        run_config: Runtime configuration describing the dataset selection constraints and temporal window.
    """
    cfg = app_config()

    match run_config.mode:
        case CliSelectionMode.LIST_SITES:
            if run_config.start_date is None or run_config.end_date is None:
                raise ValueError(f"Mode [{CliSelectionMode.LIST_SITES}] requires a start and end date")

            list_sites_selection = run_config.selection[0]
            if not isinstance(list_sites_selection, ListSitesSelection):
                raise TypeError(f"Expected ListSitesSelection, got {type(list_sites_selection).__name__}")

            run_list_sites(
                list_sites_selection.network,
                run_config.start_date,
                run_config.end_date,
                cfg,
                list_sites_selection.sites,
            )

        case CliSelectionMode.HISTORIC:
            historic_selection = run_config.selection[0]
            if not isinstance(historic_selection, HistoricSelection):
                raise TypeError(f"Expected HistoricSelection, got {type(historic_selection).__name__}")

            run_historic(historic_selection, cfg)

        case _:
            if run_config.start_date is None or run_config.end_date is None:
                raise ValueError(f"Mode [{run_config.mode}] requires a start and end date")

            run_standard(run_config.selection, run_config.start_date, run_config.end_date, cfg)


def run_standard(selection: list[Selection], start_date: datetime, end_date: datetime, cfg: AppConfig) -> None:
    """Process the selected datasets over a single date range.

    Args:
        selection: Selection specification for which datasets should be processed.
        start_date: Start of the date range to process (inclusive).
        end_date: End of the date range to process (inclusive).
        cfg: Application configuration.
    """
    network = next((s.network for s in selection if isinstance(s, DimensionSelection)), None)

    logger.info(
        f"Setting up processor: start_date={start_date}, end_date={end_date}, "
        f"network={network or 'n/a'}, selections={[str(s) for s in selection]}"
    )

    graph = _build_dependency_graph(selection, MetadataRouter(cfg.metadata_api_url), start_date, end_date)
    processor = _build_processor_from_graph(graph, start_date, end_date, cfg)
    processor.run()


def run_historic(selection: HistoricSelection, cfg: AppConfig) -> None:
    """Process every dataset for the selected sites over each site's full operating dates, one calendar year at a time.

    Args:
        selection: The network, and optionally the sites, to process.
        cfg: Application configuration.

    Raises:
        RuntimeError: If any site or year failed to process.
    """
    today = datetime.today()
    router = MetadataRouter(cfg.metadata_api_url)
    failures: list[str] = []

    site_list = _fetch_network_sites(router, selection.network, selection.sites)
    for site in site_list:
        site_name = site.site_id.removeprefix(f"{SITE_URI}/")
        if site.start_date is None:
            logger.error(f"Site [{site_name}] has no start date in its metadata, skipping.")
            failures.append(f"{site_name} (no start date)")
            continue

        site_start = site.start_date
        site_end = min(site.end_date, today) if site.end_date else today
        year_ranges = split_into_calendar_years(site_start, site_end)

        historic_selection = [DimensionSelection(network=selection.network, sites=[site.site_id])]
        logger.info(
            f"Setting up historic processor: start_date={site_start}, end_date={site_end}, "
            f"network={selection.network}, selections={[str(s) for s in historic_selection]}"
        )

        for chunk_start, chunk_end in year_ranges:
            logger.info(f"Processing chunk: start_date={chunk_start.date()}, end_date={chunk_end.date()}")
            try:
                graph = _build_dependency_graph(historic_selection, router, site_start, site_end)
                processor = _build_processor_from_graph(
                    graph, chunk_start, chunk_end, cfg, job_name_suffix=str(chunk_start.year)
                )
                processor.run()

            except Exception:
                logger.exception(f"Failed processing site [{site_name}]: {chunk_start.date()} to {chunk_end.date()}")
                failures.append(f"{site_name} ({chunk_start.date()} to {chunk_end.date()})")

    if failures:
        raise RuntimeError(f"Historic run had {len(failures)} failure(s): {failures}")


def run_list_sites(
    network: str, start_date: datetime, end_date: datetime, cfg: AppConfig, sites: list[str] | None = None
) -> None:
    """Save a JSON array of site IDs for the given network to a temporary file. Option to specify start and end dates
    to limit the listed sites to ones that were open during that date range, and/or a list of sites to limit the
    result to (still checked for network membership and open dates).

    Argo Workflows can capture it as the step result to pass to further workflow steps.

    Args:
        network: The network identifier (e.g. "cosmos").
        start_date: Start of the date range to find open sites for (inclusive).
        end_date: End of the date range to find open sites for (inclusive).
        cfg: Application configuration.
        sites: Site IDs to limit the result to. If omitted, all sites for the network are listed.
    """
    logger.info(f"Listing sites: start_date={start_date}, end_date={end_date}, network={network}")

    router = MetadataRouter(cfg.metadata_api_url)
    site_list = _fetch_network_sites(router, network, sites)

    site_ids = [
        meta.site_id.removeprefix(f"{SITE_URI}/")
        for meta in site_list
        if meta.is_active(window_start=start_date, window_end=end_date)
    ]

    logger.info(f"Found [{len(site_ids)}] sites: {site_ids}")

    output_path = "/tmp/sites.json"
    with open(output_path, "w") as f:
        json.dump(site_ids, f)


def _build_processor_from_graph(
    graph: DatasetDependencyGraph,
    start_date: datetime,
    end_date: datetime,
    cfg: AppConfig,
    job_name_suffix: str | None = None,
) -> TimeSeriesProcessor:
    """Build a TimeSeriesProcessor around an already-built dependency graph.

    Each processor gets its own data router, because running a processor closes the router's DuckDB connection.

    Args:
        graph: The built dependency graph.
        start_date: Start of the date range to process (inclusive).
        end_date: End of the date range to process (inclusive).
        cfg: Application configuration.
        job_name_suffix: Added to the pushgateway job name, so that several runs for the same site in one process
            do not overwrite each other's metrics.

    Returns:
        A TimeSeriesProcessor ready for running.
    """
    storage = _build_storage(cfg)
    reader = DuckDBParquetReader(create_duckdb_factory())
    raw_reader = RawFileReader(storage)
    writer = ByteParquetWriter(storage)
    data_router = S3DataRouter(reader, raw_reader, storage)

    job_name = f"{cfg.pushgateway_job_name}-{job_name_suffix}" if job_name_suffix else cfg.pushgateway_job_name
    metrics = Metrics(cfg.pushgateway_url, job_name, site=_resolve_site_label(graph))

    return TimeSeriesProcessor(
        graph=graph,
        data_router=data_router,
        data_writer=writer,
        start_date=start_date,
        end_date=end_date,
        metrics=metrics,
    )


def _resolve_site_label(graph: DatasetDependencyGraph) -> str:
    """Derive a metrics site label from the root sites requested for the graph.

    The graph already stores its root sites as bare site IDs, so they only need sorting into a stable order.

    Args:
        graph: The built dependency graph for this run.

    Returns:
        A comma-separated list of the site IDs requested for this run, in alphabetical order.
    """
    return ",".join(sorted(graph.root_site_ids))


def _build_storage(cfg: AppConfig) -> StorageClient:
    """Construct the storage client used for reading and writing datasets.

    Args:
        cfg: Application configuration containing storage credentials and connection details.

    Returns:
        A configured StorageClient instance.
    """
    return S3StorageClient(
        cfg.AWS_ACCESS_KEY_ID,
        cfg.AWS_SECRET_ACCESS_KEY,
        cfg.AWS_DEFAULT_REGION,
        cfg.endpoint_url,
    )


@log_duration("Dependency graph build duration: ")
def _build_dependency_graph(
    selection: list[Selection],
    metadata_router: MetadataRouter,
    start_date: datetime | None,
    end_date: datetime | None,
) -> DatasetDependencyGraph:
    """Build the dataset dependency graph for a processing run.

    Args:
        selection: Selection specification for which datasets should be processed.
        metadata_router: A router object that handles metadata API calls.
        start_date: Start of the date range to process (inclusive). If None, sites are not filtered by date.
        end_date: End of the date range to process (inclusive). If None, sites are not filtered by date.

    Returns:
        A DatasetDependencyGraph ready for execution.
    """
    logger.info("Gathering metadata and building dataset dependency graph.")
    graph = DatasetDependencyGraph(
        selection=selection, metadata_router=metadata_router, start_date=start_date, end_date=end_date
    )
    graph.build()
    logger.info(f"Found {len(graph.datasets)} datasets to process.")
    return graph


def _fetch_network_sites(router: MetadataRouter, network: str, sites: list[str] | None = None) -> list[SiteMetadata]:
    """Fetch metadata for the given sites, or for every site in the network if none are given.

    Sites that were asked for by name but belong to a different network are left out.

    Args:
        router: A router object that handles metadata API calls.
        network: The network identifier (e.g. "cosmos").
        sites: Site IDs to fetch. If omitted, all sites for the network are fetched.

    Returns:
        Metadata for each site found.
    """
    network_uri = f"{PROGRAMME_URI}/{network}"
    sites_response = router.fetch_sites(sites) if sites else router.fetch_sites_by_network(network)
    site_metadata = []
    for item in sites_response.items:
        meta = map_site_metadata(item)
        if sites and meta.network != network_uri:
            logger.warning(f"Site [{meta.site_id}] is not in network [{network}], excluding.")
            continue
        site_metadata.append(meta)
    return site_metadata
