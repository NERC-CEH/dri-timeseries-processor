from new_processor.cli.selection import RunConfig
from new_processor.configuration.app_config import app_config, AppConfig
from new_processor.dag.dataset_dependency_graph import DatasetDependencyGraph
from new_processor.io_backend.duckdb_connection import create_duckdb_factory
from new_processor.io_backend.reader import DuckDBParquetReader
from new_processor.io_backend.writer import ByteParquetWriter
from new_processor.processing.time_series_processor import TimeSeriesProcessor
from new_processor.routers.data.data_router import DuckDBDataRouter
from new_processor.routers.metadata.metadata_router import MetadataRouter
from new_processor.storage.storage_client import StorageClient, S3StorageClient


def build_processor(run_config: RunConfig) -> TimeSeriesProcessor:
    """
    Wire infrastructure and return a ready-to-run TimeSeriesProcessor.
    """
    cfg = app_config()

    metadata_router = MetadataRouter(cfg.metadata_api_url)
    storage = _build_storage(cfg)
    reader = DuckDBParquetReader(create_duckdb_factory())
    writer = ByteParquetWriter(storage)
    data_router = DuckDBDataRouter(reader)

    sites, variables, periodicities = run_config.selection.resolve()
    graph = _build_dependency_graph(run_config.network, sites, variables, periodicities, metadata_router)

    return TimeSeriesProcessor(
        graph=graph,
        data_router=data_router,
        data_writer=writer,
        start_date=run_config.start_date,
        end_date=run_config.end_date,
    )


def _build_storage(cfg: AppConfig) -> StorageClient:
    return S3StorageClient(
        cfg.AWS_ACCESS_KEY_ID,
        cfg.AWS_SECRET_ACCESS_KEY,
        cfg.AWS_DEFAULT_REGION,
        cfg.endpoint_url,
    )


def _build_dependency_graph(network, sites, variables, periodicities, metadata_router) -> DatasetDependencyGraph:
    graph = DatasetDependencyGraph(
        network=network,
        sites=sites,
        variables=variables,
        periodicities=periodicities,
        api_router=metadata_router,
    )

    graph.build()
    return graph
