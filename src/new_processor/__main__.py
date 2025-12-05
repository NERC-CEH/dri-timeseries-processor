import logging
from datetime import datetime

from new_processor.configuration.app_config import app_config
from new_processor.dag.dataset_dependency_graph import DatasetDependencyGraph
from new_processor.io_backend.duckdb_connection import create_duckdb_factory
from new_processor.io_backend.reader import DuckDBParquetReader
from new_processor.io_backend.writer import ByteParquetWriter
from new_processor.processing.time_series_processor import TimeSeriesProcessor
from new_processor.routers.data_router import DuckDBDataRouter
from new_processor.routers.metadata_router import MetadataRouter
from new_processor.storage.storage_client import S3StorageClient


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s %(message)s')

    cfg = app_config()

    router = MetadataRouter(cfg.metadata_api_url)
    storage = S3StorageClient(
        cfg.AWS_ACCESS_KEY_ID, cfg.AWS_SECRET_ACCESS_KEY, cfg.AWS_DEFAULT_REGION, cfg.endpoint_url
    )
    connection = create_duckdb_factory()
    reader = DuckDBParquetReader(connection)
    writer = ByteParquetWriter(storage)
    data_router = DuckDBDataRouter(reader)

    builder = DatasetDependencyGraph(
        "cosmos", sites=["HOLLN"], variables=["PA"], periodicity="PT30M", api_router=router
    )
    builder.build()
    DAG = builder.build_dag()

    start_date = datetime.strptime("2024-03-08", "%Y-%m-%d")
    end_date = datetime.strptime("2024-03-10", "%Y-%m-%d")

    p = TimeSeriesProcessor(builder, data_router, start_date, end_date)
    p.run()
