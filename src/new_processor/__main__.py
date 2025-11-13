import time

from dritimeseriesprocessor.configuration import app_config
from new_processor.dag.dataset_dependency_graph import DatasetDependencyGraph
from new_processor.externals.routers import MetadataRouter

if __name__ == "__main__":
    router = MetadataRouter(app_config.metadata_api_url)
    start = time.time()
    builder = DatasetDependencyGraph(
        "cosmos", sites=["BUNNY"], variables=["RN"], periodicity="PT30M", api_router=router
    )

    builder.build()
    DAG = builder.build_dag()
    end = time.time()
    print("DAG built took {} seconds".format(end - start))

    print("\n=== DAG ===")
    for idx, (node, deps) in enumerate(DAG.items()):
        print(idx, f"{node} -> {[d for d in deps]}")
