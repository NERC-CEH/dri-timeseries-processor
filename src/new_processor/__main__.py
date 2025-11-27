import time

from dritimeseriesprocessor.configuration import app_config
from new_processor.dag.dataset_dependency_graph import DatasetDependencyGraph
from new_processor.routers.metadata_router import MetadataRouter

if __name__ == "__main__":
    router = MetadataRouter(app_config.metadata_api_url)
    start = time.time()
    builder = DatasetDependencyGraph(
        "cosmos", sites=["BUNNY"], variables=["RN"], periodicity="PT30M", api_router=router
    )

    builder.build()
    DAG = builder.build_dag()
    end = time.time()
    print(f"DAG built took {end - start} seconds")

    print("\n=== DAG ===")
    for idx, (node, deps) in enumerate(DAG.items()):
        print(idx, f"{node} -> {[d for d in deps]}")

    print("\n=== DAG - flat sort ===")
    for node in builder.flat_topo_sort():
        print(node)

    print("\n=== DAG - layered sort ===")
    for idx, layer in enumerate(builder.layered_topo_sort()):
        print(f"\nLayer {idx}:")
        for node in layer:
            print(node)
