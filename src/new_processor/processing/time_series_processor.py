"""
Time series processing pipeline.

This module defines the `TimeSeriesProcessor`, which orchestrates dataset processing based on a dataset dependency
graph. It loads raw data, applies initial flagging, and carries out further processing steps according to each
dataset's method type.
"""

import logging
from datetime import datetime

from time_stream import TimeFrame

from new_processor.dag.dataset_dependency_graph import DatasetDependencyGraph
from new_processor.domain_models.time_series_container import TimeSeriesContainer
from new_processor.operations.flags.flag_operations import add_initial_core_flags
from new_processor.operations.quality_control.apply_qc import run_quality_control
from new_processor.routers.data_router import DataRouter
from new_processor.utils.enums import MethodType


logger = logging.getLogger(__name__)


class TimeSeriesProcessor:
    """Orchestrates the dataset processing pipeline.

    The processor traverses the graph in topological layers and processes each dataset in turn.
    """

    def __init__(
        self,
        graph: DatasetDependencyGraph,
        data_router: DataRouter,
        start_date: datetime,
        end_date: datetime,
    ):
        """Initialise the processor.

        Args:
            graph: Dependency graph containing dataset relationships and repository of dataset containers.
            data_router: Router for retrieving raw data from storage.
            start_date: Start of the date range to process (inclusive).
            end_date: End of the date range to process (inclusive).
        """
        self.graph = graph
        self.data_router = data_router
        self.start_date = start_date
        self.end_date = end_date

    def run(self) -> None:
        """Execute the processing pipeline by iterating through the dependency graph.
        The graph is traversed in order, ensuring dependencies are processed before the datasets that rely on them.
        """
        layers = self.graph.layered_topo_sort()
        logger.info("Processing pipeline started.")

        for layer_idx, layer in enumerate(layers):
            logger.info(f"Processing layer {layer_idx}: {layer}")
            for dataset_id in layer:
                self.process_dataset(dataset_id)

        logger.info("Processing pipeline completed successfully.")

    def process_dataset(self, dataset_id: str) -> None:
        """Process a single dataset according to the configured method type in its metadata.

        Args:
            dataset_id: The dataset to process.
        """

        container = self.graph.datasets[dataset_id]

        match container.method_type:
            case MethodType.LOAD:
                self._load_raw(container)

            case MethodType.PROCESS:
                self._process(container)

            case MethodType.AGGREGATION:
                print("aggregate", container.method)

            case MethodType.DERIVATION:
                print("derive", container.method)

    def _load_raw(self, container: TimeSeriesContainer) -> None:
        """Load raw time-series data for a dataset and initialise a `TimeFrame`.

        The DataRouter is used to retrieve the data, which is then wrapped into a `TimeFrame` with resolution and
        periodicity from metadata. Core flags are initialised and the resulting `TimeFrame` is stored on the
        container.

        Args:
            container: Time series container of metadata and data.
        """
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

    def _process(self, container):
        # TODO: The "process" method is actually done on the 'raw' version of the processed dataset.
        #  that's where all the configs will be found.
        #  The 'raw' dataset is held in the direct_depends_on, which we are assuming will only have one item.
        #  Is this robust?
        dep_id = container.direct_depends_on[0]
        dep_container = self.graph.datasets[dep_id]

       # print("do corrections", dep_container.correction_configs)

        if dep_container.qc_configs:
            tf = run_quality_control(dep_container, self.graph.datasets)
            container.data = tf

    #    print("do infill", dep_container.infill_configs)