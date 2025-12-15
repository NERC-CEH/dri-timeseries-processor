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

from datetime import date, datetime

from new_processor.cli.selection import RunConfig, SelectionSpec
from new_processor.configuration.app_config import AppConfig, app_config
from new_processor.dag.dataset_dependency_graph import DatasetDependencyGraph
from new_processor.io_backend.duckdb_connection import create_duckdb_factory
from new_processor.io_backend.reader import DuckDBParquetReader
from new_processor.io_backend.writer import ByteParquetWriter
from new_processor.processing.time_series_processor import TimeSeriesProcessor
from new_processor.routers.data.data_router import DuckDBDataRouter
from new_processor.routers.metadata.metadata_router import MetadataRouter
from new_processor.storage.storage_client import S3StorageClient, StorageClient


def run_from_config(run_config: RunConfig) -> None:
    """Execute a processing run from a valid RunConfig made of user args.

    Resolve the dataset selection defined in the RunConfig, construct a fully-configured
    TimeSeriesProcessor, and trigger execution of the processing workflow.

    Args:
        run_config: Runtime configuration describing the network, dataset selection constraints, and temporal window.
    """
    processor = _build_processor(run_config.network, run_config.selection, run_config.start_date, run_config.end_date)
    processor.run()


def _build_processor(
    network: str,
    selection: SelectionSpec,
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
    cfg = app_config()

    metadata_router = MetadataRouter(cfg.metadata_api_url)
    storage = _build_storage(cfg)
    reader = DuckDBParquetReader(create_duckdb_factory())
    writer = ByteParquetWriter(storage)
    data_router = DuckDBDataRouter(reader)

    graph = _build_dependency_graph(network, selection, metadata_router)

    return TimeSeriesProcessor(
        graph=graph,
        data_router=data_router,
        data_writer=writer,
        start_date=start_date,
        end_date=end_date,
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


def _build_dependency_graph(network, selection, metadata_router) -> DatasetDependencyGraph:
    """Build the dataset dependency graph for a processing run.

    Args:
        network: Network identifier.
        selection: Selection specification for which datasets should be processed.
        metadata_router: A router object that handles metadata API calls.

    Returns:
        A DatasetDependencyGraph ready for execution.
    """
    graph = DatasetDependencyGraph(network=network, selection=selection, metadata_router=metadata_router)
    graph.build()
    return graph
