import time
from datetime import datetime

from new_processor.configuration.app_config import app_config
from new_processor.dag.dataset_dependency_graph import DatasetDependencyGraph
from new_processor.routers.data_router import DuckDBDataRouter
from new_processor.routers.metadata_router import MetadataRouter

# from new_processor.routers.data_router import S3DataRouter
from new_processor.storage.storage_client import S3StorageClient
from new_processor.processing.time_series_processor import TimeSeriesProcessor
from new_processor.io_backend.reader import DuckDBParquetReader
from new_processor.io_backend.writer import ByteParquetWriter
from new_processor.io_backend.duckdb_connection import create_duckdb_factory

if __name__ == "__main__":
    cfg = app_config()

    router = MetadataRouter(cfg.metadata_api_url)

    start = time.time()
    builder = DatasetDependencyGraph(
        "cosmos", sites=["BUNNY"], variables=["LWIN"], periodicity="PT30M", api_router=router
    )

    builder.build()
    DAG = builder.build_dag()

    end = time.time()
    print(f"DAG built took {end - start} seconds")

    storage = S3StorageClient(
        cfg.AWS_ACCESS_KEY_ID, cfg.AWS_SECRET_ACCESS_KEY, cfg.AWS_DEFAULT_REGION, cfg.endpoint_url
    )
    connection = create_duckdb_factory()
    reader = DuckDBParquetReader(connection)
    writer = ByteParquetWriter(storage)

    data_router = DuckDBDataRouter(reader)

    start_date = datetime.strptime("2024-03-08", "%Y-%m-%d")
    end_date = datetime.strptime("2024-03-10", "%Y-%m-%d")

    p = TimeSeriesProcessor(builder, data_router, start_date, end_date)
    p.run()

    # print("\n=== DAG ===")
    # for idx, (node, deps) in enumerate(DAG.items()):
    #     print(idx, f"{node} -> {[d for d in deps]}")
    #
    # print("\n=== DAG - flat sort ===")
    # for node in builder.flat_topo_sort():
    #     print(node)
    #
    # print("\n=== DAG - layered sort ===")
    # for idx, layer in enumerate(builder.layered_topo_sort()):
    #     print(f"\nLayer {idx}:")
    #     for node in layer:
    #         print(node)
