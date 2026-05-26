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
from datetime import date, datetime

from dritimeseriesprocessor.cli.selection import RunConfig, SelectionOption
from dritimeseriesprocessor.configuration.app_config import AppConfig, app_config
from dritimeseriesprocessor.dag.dataset_dependency_graph import DatasetDependencyGraph
from dritimeseriesprocessor.io_backend.duckdb_connection import create_duckdb_factory
from dritimeseriesprocessor.io_backend.flux_io import FluxS3Client
from dritimeseriesprocessor.io_backend.reader import DuckDBParquetReader
from dritimeseriesprocessor.io_backend.writer import ByteParquetWriter
from dritimeseriesprocessor.metrics.metrics import Metrics
from dritimeseriesprocessor.models.mappers.api_to_domain import map_site_metadata
from dritimeseriesprocessor.processing.time_series_processor import TimeSeriesProcessor
from dritimeseriesprocessor.routers.data.data_router import DuckDBDataRouter
from dritimeseriesprocessor.routers.metadata.flux_metadata_loader import FluxMetadataLoader
from dritimeseriesprocessor.routers.metadata.metadata_router import MetadataRouter
from dritimeseriesprocessor.storage.storage_client import S3StorageClient, StorageClient
from dritimeseriesprocessor.utils.enums import CliSelectionMode
from dritimeseriesprocessor.utils.timer import log_duration
from dritimeseriesprocessor.utils.urls import SITE_URI

logger = logging.getLogger(__name__)


@log_duration("Total time taken: ", header=True)
def run_from_config(run_config: RunConfig) -> None:
    """Execute a processing run from a valid RunConfig made of user args.

    Resolve the dataset selection defined in the RunConfig, construct a fully-configured
    TimeSeriesProcessor, and trigger execution of the processing workflow.

    Args:
        run_config: Runtime configuration describing the network, dataset selection constraints, and temporal window.
    """
    if run_config.mode == CliSelectionMode.LIST_SITES:
        list_sites(run_config.network, run_config.start_date, run_config.end_date)
        return

    processor = _build_processor(
        run_config.network,
        run_config.selection,
        run_config.start_date,
        run_config.end_date,
        run_config.mode,
    )
    processor.run()


def _build_processor(
    network: str,
    selection: list[SelectionOption],
    start_date: datetime,
    end_date: datetime,
    mode: CliSelectionMode,
) -> TimeSeriesProcessor:
    """Build a TimeSeriesProcessor object.

    Assembles all required runtime dependencies, including metadata access, data routing, storage backends, and the
    dataset dependency graph, into a ready-to-run TimeSeriesProcessor instance.

    Args:
        network: Network identifier.
        selection: Selection specification for which datasets should be processed.
        start_date: Start of the date range to process (inclusive).
        end_date: End of the date range to process (inclusive).

    Returns:
        A TimeSeriesProcessor ready for running.
    """
    logger.info("-" * 30)
    logger.info("Setting up processor for selections:")
    logger.info(f"Start date            : {start_date}")
    logger.info(f"End date              : {end_date}")
    logger.info(f"Network               : {network}")
    logger.info(f"Dataset selections    : {'\n' + '\n'.join([str(s) for s in selection])}")
    logger.info("-" * 30)

    cfg = app_config()

    metadata_router = MetadataRouter(cfg.metadata_api_url)
    storage = _build_storage(cfg)
    reader = DuckDBParquetReader(create_duckdb_factory())
    writer = ByteParquetWriter(storage)
    data_router = DuckDBDataRouter(reader)
    metrics = Metrics(cfg.pushgateway_url, "timeseries-processor")

    if mode == CliSelectionMode.EDDYPRO:
        selected_sites: list[str] = []
        for item in selection:
            selected_sites.extend(item.sites or [])

        loader = FluxMetadataLoader(network=network, sites=selected_sites or None)
        local_graph_data = loader.load()
        graph = DatasetDependencyGraph(
            network=network,
            selection=selection,
            metadata_router=metadata_router,
            start_date=start_date,
            end_date=end_date,
        )
        graph.datasets = local_graph_data.datasets
        graph.site_metadata = local_graph_data.site_metadata
    else:
        graph = _build_dependency_graph(network, selection, metadata_router, start_date, end_date)

    flux_s3_client = FluxS3Client(storage_client=storage) if mode == CliSelectionMode.EDDYPRO else None

    return TimeSeriesProcessor(
        graph=graph,
        data_router=data_router,
        data_writer=writer,
        start_date=start_date,
        end_date=end_date,
        metrics=metrics,
        flux_s3_client=flux_s3_client,
    )


def _build_storage(cfg: AppConfig) -> StorageClient:
    """Construct the storage client used for reading and writing datasets.

    Args:
        cfg: Application configuration containing storage credentials and connection details.

    Returns:
        A configured StorageClient instance.
    """
    assert cfg.AWS_ACCESS_KEY_ID is not None, "AWS_ACCESS_KEY_ID must be set"
    assert cfg.AWS_SECRET_ACCESS_KEY is not None, "AWS_SECRET_ACCESS_KEY must be set"
    return S3StorageClient(
        cfg.AWS_ACCESS_KEY_ID,
        cfg.AWS_SECRET_ACCESS_KEY,
        cfg.AWS_DEFAULT_REGION,
        cfg.endpoint_url,
    )


@log_duration("Dependency graph build duration: ", footer=True)
def _build_dependency_graph(
    network: str,
    selection: list[SelectionOption],
    metadata_router: MetadataRouter,
    start_date: datetime,
    end_date: datetime,
) -> DatasetDependencyGraph:
    """Build the dataset dependency graph for a processing run.

    Args:
        network: Network identifier.
        selection: Selection specification for which datasets should be processed.
        metadata_router: A router object that handles metadata API calls.
        start_date: Start of the date range to process (inclusive).
        end_date: End of the date range to process (inclusive).

    Returns:
        A DatasetDependencyGraph ready for execution.
    """
    logger.info("Gathering metadata and building dataset dependency graph.")
    graph = DatasetDependencyGraph(
        network=network, selection=selection, metadata_router=metadata_router, start_date=start_date, end_date=end_date
    )
    graph.build()
    logger.info(f"Found {len(graph.datasets)} datasets to process.")
    return graph


def list_sites(network: str, start_date: date | datetime, end_date: date | datetime) -> None:
    """Save a JSON array of site IDs for the given network to a temporary file. Option to specify start and end dates
    to limit the listed sites to ones that were open during that date range.

    Argo Workflows can capture it as the step result to pass to further workflow steps.

    Args:
        network: The network identifier (e.g. "cosmos").
        start_date: Start of the date range to find open sites for (inclusive).
        end_date: End of the date range to find open sites for (inclusive).
    """
    logger.info("-" * 30)
    logger.info("Listing sites for selections:")
    logger.info(f"Start date : {start_date}")
    logger.info(f"End date   : {end_date}")
    logger.info(f"Network    : {network}")
    logger.info("-" * 30)

    cfg = app_config()
    router = MetadataRouter(cfg.metadata_api_url)

    sites_response = router.fetch_sites_by_network(network)
    site_ids = []
    for item in sites_response.items:
        meta = map_site_metadata(item)
        active_start = (
            datetime.combine(start_date, datetime.min.time())
            if isinstance(start_date, date) and not isinstance(start_date, datetime)
            else start_date
        )
        active_end = (
            datetime.combine(end_date, datetime.min.time())
            if isinstance(end_date, date) and not isinstance(end_date, datetime)
            else end_date
        )
        if meta.is_active(window_start=active_start, window_end=active_end):
            site_ids.append(meta.site_id.removeprefix(f"{SITE_URI}/"))

    logger.info(f"Found [{len(site_ids)}] sites: {site_ids}")

    output_path = "/tmp/sites.json"
    with open(output_path, "w") as f:
        json.dump(site_ids, f)
