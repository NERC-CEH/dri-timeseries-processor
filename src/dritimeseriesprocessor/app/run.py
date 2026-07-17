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

from dritimeseriesprocessor.cli.selection import DimensionSelection, ListSitesSelection, RunConfig, Selection
from dritimeseriesprocessor.configuration.app_config import AppConfig, app_config
from dritimeseriesprocessor.dag.dataset_dependency_graph import DatasetDependencyGraph
from dritimeseriesprocessor.io_backend.duckdb_connection import create_duckdb_factory
from dritimeseriesprocessor.io_backend.reader import DuckDBParquetReader, RawFileReader
from dritimeseriesprocessor.io_backend.writer import ByteParquetWriter
from dritimeseriesprocessor.metrics.metrics import Metrics
from dritimeseriesprocessor.models.mappers.api_to_domain import map_site_metadata
from dritimeseriesprocessor.processing.time_series_processor import TimeSeriesProcessor
from dritimeseriesprocessor.routers.data.data_router import S3DataRouter
from dritimeseriesprocessor.routers.metadata.metadata_router import MetadataRouter
from dritimeseriesprocessor.storage.storage_client import S3StorageClient, StorageClient
from dritimeseriesprocessor.utils.enums import CliSelectionMode
from dritimeseriesprocessor.utils.timer import log_duration
from dritimeseriesprocessor.utils.urls import SITE_URI

logger = logging.getLogger(__name__)


@log_duration("Total time taken: ")
def run_from_config(run_config: RunConfig) -> None:
    """Execute a processing run from a valid RunConfig made of user args.

    Resolve the dataset selection defined in the RunConfig, construct a fully-configured
    TimeSeriesProcessor, and trigger execution of the processing workflow.

    Args:
        run_config: Runtime configuration describing the dataset selection constraints and temporal window.
    """
    if run_config.mode == CliSelectionMode.LIST_SITES:
        list_sites_selection = run_config.selection[0]
        if not isinstance(list_sites_selection, ListSitesSelection):
            raise TypeError(f"Expected ListSitesSelection, got {type(list_sites_selection).__name__}")
        list_sites(list_sites_selection.network, run_config.start_date, run_config.end_date)
        return

    processor = _build_processor(
        run_config.selection,
        run_config.start_date,
        run_config.end_date,
    )
    processor.run()


def _build_processor(
    selection: list[Selection],
    start_date: datetime,
    end_date: datetime,
) -> TimeSeriesProcessor:
    """Build a TimeSeriesProcessor object.

    Assembles all required runtime dependencies, including metadata access, data routing, storage backends, and the
    dataset dependency graph, into a ready-to-run TimeSeriesProcessor instance.

    Args:
        selection: Selection specification for which datasets should be processed.
        start_date: Start of the date range to process (inclusive).
        end_date: End of the date range to process (inclusive).

    Returns:
        A TimeSeriesProcessor ready for running.
    """
    network = next((s.network for s in selection if isinstance(s, DimensionSelection)), None)

    logger.info(
        f"Setting up processor: start_date={start_date}, end_date={end_date}, "
        f"network={network or 'n/a'}, selections={[str(s) for s in selection]}"
    )

    cfg = app_config()

    metadata_router = MetadataRouter(cfg.metadata_api_url)
    storage = _build_storage(cfg)
    reader = DuckDBParquetReader(create_duckdb_factory())
    raw_reader = RawFileReader(storage)
    writer = ByteParquetWriter(storage)
    data_router = S3DataRouter(reader, raw_reader)
    metrics = Metrics(cfg.pushgateway_url, "timeseries-processor")

    graph = _build_dependency_graph(selection, metadata_router, start_date, end_date)

    return TimeSeriesProcessor(
        graph=graph,
        data_router=data_router,
        data_writer=writer,
        start_date=start_date,
        end_date=end_date,
        metrics=metrics,
    )


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
    start_date: datetime,
    end_date: datetime,
) -> DatasetDependencyGraph:
    """Build the dataset dependency graph for a processing run.

    Args:
        selection: Selection specification for which datasets should be processed.
        metadata_router: A router object that handles metadata API calls.
        start_date: Start of the date range to process (inclusive).
        end_date: End of the date range to process (inclusive).

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


def list_sites(network: str, start_date: datetime, end_date: datetime) -> None:
    """Save a JSON array of site IDs for the given network to a temporary file. Option to specify start and end dates
    to limit the listed sites to ones that were open during that date range.

    Argo Workflows can capture it as the step result to pass to further workflow steps.

    Args:
        network: The network identifier (e.g. "cosmos").
        start_date: Start of the date range to find open sites for (inclusive).
        end_date: End of the date range to find open sites for (inclusive).
    """
    logger.info(f"Listing sites: start_date={start_date}, end_date={end_date}, network={network}")

    cfg = app_config()
    router = MetadataRouter(cfg.metadata_api_url)

    sites_response = router.fetch_sites_by_network(network)
    site_ids = []
    for item in sites_response.items:
        meta = map_site_metadata(item)
        if meta.is_active(window_start=start_date, window_end=end_date):
            site_ids.append(meta.site_id.removeprefix(f"{SITE_URI}/"))

    logger.info(f"Found [{len(site_ids)}] sites: {site_ids}")

    output_path = "/tmp/sites.json"
    with open(output_path, "w") as f:
        json.dump(site_ids, f)
