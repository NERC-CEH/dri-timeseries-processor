import logging
from datetime import datetime

from time_stream import TimeFrame

from new_processor.dag.dataset_dependency_graph import DatasetDependencyGraph
from new_processor.domain_models.time_series_container import TimeSeriesContainer
from new_processor.operations.flags.flag_operations import add_initial_core_flags
from new_processor.routers.data_router import DataRouter
from new_processor.utils.enums import MethodType

logger = logging.getLogger(__name__)


class TimeSeriesProcessor:
    def __init__(
        self,
        graph: DatasetDependencyGraph,
        data_router: DataRouter,
        start_date: datetime,
        end_date: datetime,
    ):
        self.graph = graph
        self.data_router = data_router
        self.start_date = start_date
        self.end_date = end_date

    def run(self) -> None:
        layers = self.graph.layered_topo_sort()
        logger.info("Processing pipeline started.")

        for layer_idx, layer in enumerate(layers):
            logger.info(f"Processing layer {layer_idx}: {layer}")
            for dataset_id in layer:
                self.process_dataset(dataset_id)

        logger.info("Processing pipeline completed successfully.")

    def process_dataset(self, dataset_id: str) -> None:
        container = self.graph.datasets[dataset_id]
        print("\n", dataset_id)

        match container.method_type:
            case MethodType.LOAD:
                self._load_raw(container)

            case MethodType.PROCESS:
                # TODO: The "process" method is actually done on the 'raw' version of the processed dataset.
                #  that's where all the configs will be found.
                #  The 'raw' dataset is held in the direct_depends_on, which we are assuming will only have one item.
                #  Is this robust?
                dep_container = self.graph.datasets[container.direct_depends_on[0]]
                print("do corrections", dep_container.correction_configs)
                print("do qc", dep_container.qc_configs)
                print("do infill", dep_container.infill_configs)

            case MethodType.AGGREGATION:
                print("aggregate", container.method)

            case MethodType.DERIVATION:
                print("derive", container.method)

    def _load_raw(self, container: TimeSeriesContainer) -> None:
        print("load raw", container.source_bucket)

        df = self.data_router.query_by_date_range(container, self.start_date, self.end_date)

        # TODO: Note issue about the "time" name - where to get this in metadata
        tf = TimeFrame(
            df=df,
            time_name="time",
            resolution=container.resolution,
            periodicity=container.periodicity,
        ).with_metadata(
            {
                "site_id": container.source_site,
                "column_name": container.source_column,
                "processing_level": container.processing_level,
            }
        )

        tf = add_initial_core_flags(tf)
        container.data = tf
        print(tf)
