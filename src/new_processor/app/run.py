from new_processor.cli.models import RunConfig
from new_processor.cli.resolver import DatasetKey, SelectionResolver
from new_processor.configuration.app_config import app_config
from new_processor.dag.dataset_dependency_graph import DatasetDependencyGraph
from new_processor.io_backend.duckdb_connection import create_duckdb_factory
from new_processor.io_backend.reader import DuckDBParquetReader
from new_processor.io_backend.writer import ByteParquetWriter
from new_processor.processing.time_series_processor import TimeSeriesProcessor
from new_processor.routers.data.data_router import DuckDBDataRouter
from new_processor.routers.metadata.metadata_router import MetadataRouter
from new_processor.storage.storage_client import S3StorageClient


def run_from_config(run_config: RunConfig) -> None:
    """Execute a processing run from a validated RunConfig."""
    selection_resolver = SelectionResolver()
    selection = selection_resolver.resolve(run_config.selection)

    # Build and run the processor
    processor = build_processor(run_config, selection)
    processor.run()


def build_processor(run_config: RunConfig, selection: list[DatasetKey]) -> TimeSeriesProcessor:
    """
    Wire infrastructure and return a ready-to-run TimeSeriesProcessor.
    """

    cfg = app_config()

    metadata_router = MetadataRouter(cfg.metadata_api_url)

    storage = S3StorageClient(
        cfg.AWS_ACCESS_KEY_ID,
        cfg.AWS_SECRET_ACCESS_KEY,
        cfg.AWS_DEFAULT_REGION,
        cfg.endpoint_url,
    )

    reader = DuckDBParquetReader(create_duckdb_factory())
    writer = ByteParquetWriter(storage)
    data_router = DuckDBDataRouter(reader)

    sites = [key.site for key in selection]
    variables = [key.column for key in selection]
    periodicities = [key.periodicity for key in selection]

    graph = DatasetDependencyGraph(
        network=run_config.network,
        sites=sites,
        variables=variables,
        periodicities=periodicities,
        api_router=metadata_router,
    )

    graph.build()
    graph.build_dag()

    return TimeSeriesProcessor(
        graph=graph,
        data_router=data_router,
        data_writer=writer,
        start_date=run_config.start_date,
        end_date=run_config.end_date,
    )
