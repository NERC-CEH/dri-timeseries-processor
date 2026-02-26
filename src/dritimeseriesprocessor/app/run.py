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

import logging
from datetime import date, datetime

from dritimeseriesprocessor import PACKAGE_ROOT
from dritimeseriesprocessor.cli.selection import RunConfig, SelectionOption
from dritimeseriesprocessor.configuration.app_config import AppConfig, app_config
from dritimeseriesprocessor.dag.dataset_dependency_graph import DatasetDependencyGraph
from dritimeseriesprocessor.io_backend.duckdb_connection import create_duckdb_factory
from dritimeseriesprocessor.io_backend.reader import DuckDBParquetReader
from dritimeseriesprocessor.io_backend.writer import ByteParquetWriter
from dritimeseriesprocessor.metrics.metrics import Metrics
from dritimeseriesprocessor.processing.eddypro_processor import EddyProProcessor
from dritimeseriesprocessor.processing.time_series_processor import TimeSeriesProcessor
from dritimeseriesprocessor.routers.data.data_router import DuckDBDataRouter
from dritimeseriesprocessor.routers.data.flux_data_router import FluxDataRouter
from dritimeseriesprocessor.routers.metadata.flux_metadata_loader import FluxMetadataLoader
from dritimeseriesprocessor.routers.metadata.metadata_router import MetadataRouter
from dritimeseriesprocessor.storage.storage_client import S3StorageClient, StorageClient
from dritimeseriesprocessor.utils.enums import CliSelectionMode
from dritimeseriesprocessor.utils.timer import log_duration

logger = logging.getLogger(__name__)


@log_duration("Total time taken: ", header=True)
def run_from_config(run_config: RunConfig) -> None:
    """Execute a processing run from a valid RunConfig made of user args.

    Resolve the dataset selection defined in the RunConfig, construct a fully-configured
    TimeSeriesProcessor, and trigger execution of the processing workflow.

    Args:
        run_config: Runtime configuration describing the network, dataset selection constraints, and temporal window.
    """
    if run_config.mode == CliSelectionMode.EDDYPRO:
        _run_eddypro(run_config)
        return

    processor = _build_processor(run_config.network, run_config.selection, run_config.start_date, run_config.end_date)
    processor.run()


def _run_eddypro(run_config: RunConfig) -> None:
    """Run EddyPro processing.

    For local development, metadata is loaded from JSON fixtures via FluxMetadataLoader.
    This produces the same domain model objects (TimeSeriesContainer, SiteMetadata) that
    the real MetadataRouter + DAG builder would produce in production.
    """
    cfg = app_config()
    storage = _build_storage(cfg)
    flux_router = FluxDataRouter(storage)

    # Extract site identifiers from selection options
    sites = _extract_sites_from_selection(run_config.selection)

    loader = FluxMetadataLoader(network=run_config.network, sites=sites)
    datasets = loader.load_datasets()
    site_metadata = loader.load_site_metadata()

    # Build a dependency graph for ordering (mirrors the time-series pipeline).
    # For local runs we populate it from fixtures; in production this should be built
    # from the metadata API via `graph.build()`.
    graph = DatasetDependencyGraph(
        metadata_router=MetadataRouter(cfg.metadata_api_url),
        network=run_config.network,
        selection=run_config.selection,
    )
    graph.datasets = datasets
    graph.site_metadata = site_metadata

    templates_dir = PACKAGE_ROOT / "__assets__" / "eddypro_templates"

    processor = EddyProProcessor(
        graph=graph,
        flux_data_router=flux_router,
        project_template=templates_dir / "processing_template.eddypro",
        metadata_template=templates_dir / "metadata_template.metadata",
        start_date=run_config.start_date,
        end_date=run_config.end_date,
    )
    processor.run()


def _extract_sites_from_selection(selection: list[SelectionOption]) -> list[str]:
    """Extract a deduplicated, sorted list of site identifiers from selection options.

    Args:
        selection: Selection options from the RunConfig.

    Returns:
        Sorted list of unique site identifiers.
    """
    sites = set()
    for option in selection:
        if option.sites:
            sites.update(option.sites)
    return sorted(sites)


def _build_processor(
    network: str,
    selection: list[SelectionOption],
    start_date: date | datetime,
    end_date: date | datetime,
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

    graph = _build_dependency_graph(network, selection, metadata_router)

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


@log_duration("Dependency graph build duration: ", footer=True)
def _build_dependency_graph(
    network: str, selection: list[SelectionOption], metadata_router: MetadataRouter
) -> DatasetDependencyGraph:
    """Build the dataset dependency graph for a processing run.

    Args:
        network: Network identifier.
        selection: Selection specification for which datasets should be processed.
        metadata_router: A router object that handles metadata API calls.

    Returns:
        A DatasetDependencyGraph ready for execution.
    """
    logger.info("Gathering metadata and building dataset dependency graph.")
    graph = DatasetDependencyGraph(network=network, selection=selection, metadata_router=metadata_router)
    graph.build()
    logger.info(f"Found {len(graph.datasets)} datasets to process.")
    return graph
