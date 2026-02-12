"""
Time series processing pipeline.

This module defines the `TimeSeriesProcessor`, which orchestrates dataset processing based on a dataset dependency
graph. It loads raw data, applies initial flagging, and carries out further processing steps according to each
dataset's method type.
"""

import logging
from collections import defaultdict
from concurrent.futures import as_completed, ThreadPoolExecutor
from datetime import date, datetime

from time_stream import TimeFrame

from dritimeseriesprocessor.dag.dataset_dependency_graph import DatasetDependencyGraph
from dritimeseriesprocessor.io_backend.writer import ParquetWriterInterface
from dritimeseriesprocessor.metrics.metrics import Metrics
from dritimeseriesprocessor.models.domain_models.time_series_container import TimeSeriesContainer, check_common_attributes
from dritimeseriesprocessor.operations.aggregation.aggregation_pipeline import AggregationPipeline
from dritimeseriesprocessor.operations.correction.correction_pipeline import CorrectionPipeline
from dritimeseriesprocessor.operations.derivation.derivation_pipeline import DerivationPipeline
from dritimeseriesprocessor.operations.flags.flag_methods import add_initial_core_flags
from dritimeseriesprocessor.operations.infill.infill_pipeline import InfillPipeline
from dritimeseriesprocessor.operations.quality_control.qc_pipeline import QCPipeline
from dritimeseriesprocessor.routers.data.data_router import DataRouter
from dritimeseriesprocessor.utils.enums import MethodType, OperationType, ProcessingLevel
from dritimeseriesprocessor.utils.polars_utils import split_by_date
from dritimeseriesprocessor.utils.time_stream_utils import merge_multiple_timeframes

logger = logging.getLogger(__name__)


OPERATION_PIPELINES = {
    OperationType.CORRECTION: CorrectionPipeline(),
    OperationType.QUALITY_CONTROL: QCPipeline(),
    OperationType.INFILLING: InfillPipeline(),
    OperationType.AGGREGATION: AggregationPipeline(),
    OperationType.DERIVATION: DerivationPipeline(),
}


class TimeSeriesProcessor:
    """Orchestrates the dataset processing pipeline.

    The processor traverses the graph in topological layers and processes each dataset in turn.
    """

    def __init__(
        self,
        graph: DatasetDependencyGraph,
        data_router: DataRouter,
        data_writer: ParquetWriterInterface,
        start_date: date | datetime,
        end_date: date | datetime,
        metrics: Metrics,
    ):
        """Initialise the processor.

        Args:
            graph: Dependency graph containing dataset relationships and repository of dataset containers.
            data_router: Router for retrieving raw data from storage.
            data_writer: Handles writing data to parquet files.
            start_date: Start of the date range to process (inclusive).
            end_date: End of the date range to process (inclusive).
        """
        self.graph = graph
        self.data_router = data_router
        self.data_writer = data_writer
        self.start_date = start_date
        self.end_date = end_date
        self.metrics = metrics

    def run(self) -> None:
        """Execute the processing pipeline by iterating through the dependency graph.
        The graph is traversed in order, ensuring dependencies are processed before the datasets that rely on them.
        """
        with self.metrics.time_pipeline.time():
            if not self.graph.datasets:
                logger.error("No datasets found in dependency graph.")
            else:
                layers = self.graph.layered_topo_sort()
                logger.info("Processing pipeline started.")

                for layer in layers:
                    self.process_layer(layer)

                self._save_datasets()

        logger.info("Processing pipeline finished. Pushing prometheus metrics.")
        self.metrics.export_metrics_to_pushgateway()

    def process_layer(self, layer: list[str]) -> None:
        """Process an individual layer of the dependency graph.

        Args:
            layer: Datasets to process
        """
        logger.info(f"Processing layer: {layer}")
        for dataset_id in layer:
            try:
                self.process_dataset(dataset_id)
            except Exception:
                self.metrics.failed.inc()
                logger.exception(f"Processing failed for: {dataset_id}")
            else:
                self.metrics.success.inc()

    def process_dataset(self, dataset_id: str) -> None:
        """Process a single dataset according to the configured method type in its metadata.

        Args:
            dataset_id: The dataset to process.
        """

        container = self.graph.datasets[dataset_id]

        match container.method_type():
            case MethodType.LOAD:
                self._load_raw(container)

            case MethodType.PROCESS:
                self._process(container)

            case MethodType.AGGREGATION:
                self._aggregate(container)

            case MethodType.DERIVATION:
                self._derive(container)

    def _load_raw(self, container: TimeSeriesContainer) -> None:
        """Load raw time-series data for a dataset and initialise a `TimeFrame`.

        The DataRouter is used to retrieve the data, which is then wrapped into a `TimeFrame` with resolution and
        periodicity from metadata. Core flags are initialised and the resulting `TimeFrame` is stored on the
        container.

        Args:
            container: Time series container of metadata and data for the dataset to load.
        """
        with self.metrics.time_load.time():
            logger.info(f"{MethodType.LOAD}: {container.ts_id}")
            df = self.data_router.query_by_date_range(container, self.start_date, self.end_date)

            if df.is_empty():
                logger.warning(f"No data returned for dataset: {container.ts_id}")
                self.metrics.no_data.inc()

            else:
                tf = (
                    TimeFrame(
                        df=df,
                        time_name=container.time_column_name,
                        resolution=container.resolution,
                        periodicity=container.periodicity,
                    )
                    .with_metadata({"column_name": container.source_column})
                    .pad()
                )

                tf = add_initial_core_flags(tf)
                container.data = tf

    def _process(self, container: TimeSeriesContainer) -> None:
        """Process a single dataset according to the data processing configurations attached via metadata.

        This runs the operations of: Corrections, Quality Control and Infilling (in that order) to the given dataset.
        Each operation type has a pipeline class responsible for the specifics of how that method is carried out.

        Args:
            container: Time series container of metadata and data for the dataset to process.
        """
        logger.info(f"{MethodType.PROCESS}: {container.ts_id}")

        dep_container = self._get_single_dependency(container)

        with self.metrics.time_corrections.time():
            pipeline = OPERATION_PIPELINES[OperationType.CORRECTION]
            dep_container.data = pipeline.run(dep_container, self.graph.datasets)

        with self.metrics.time_qc.time():
            pipeline = OPERATION_PIPELINES[OperationType.QUALITY_CONTROL]
            dep_container.data = pipeline.run(dep_container, self.graph.datasets)

        with self.metrics.time_infill.time():
            pipeline = OPERATION_PIPELINES[OperationType.INFILLING]
            dep_container.data = pipeline.run(dep_container, self.graph.datasets)

        # shift the data into the primary container
        container.data = dep_container.data

    def _aggregate(self, container: TimeSeriesContainer) -> None:
        """Run aggregation to create a single dataset according to the method configurations attached via metadata.

        Args:
            container: Time series container of metadata and data for dataset to create via aggregation.
        """
        logger.info(f"{MethodType.AGGREGATION}: {container.ts_id}")

        with self.metrics.time_aggregate.time():
            pipeline = OPERATION_PIPELINES[OperationType.AGGREGATION]
            container.data = pipeline.run(container, self.graph.datasets)

    def _derive(self, container: TimeSeriesContainer) -> None:
        """Run derivation to create a single dataset according to the method configurations attached via metadata.

        Args:
            container: Time series container of metadata and data for dataset to create via derivation.
        """
        logger.info(f"{MethodType.DERIVATION}: {container.ts_id}")

        with self.metrics.time_derive.time():
            pipeline = OPERATION_PIPELINES[OperationType.DERIVATION]
            container.data = pipeline.run(container, self.graph.datasets)

    def _get_single_dependency(self, container: TimeSeriesContainer) -> TimeSeriesContainer:
        """Get the dependent time series container of the given container where it is assumed that there is only
        a single dependency.

        Args:
            container: Time series container for the dataset to fetch single dependency

        Returns:
            Dependent time series container.
        """
        dependencies = container.all_dependencies()
        num_dependents = len(dependencies)
        if num_dependents != 1:
            raise ValueError(f"Expected a single dependent dataset. Found: {num_dependents}")

        dep_id = dependencies[0]
        return self.graph.datasets[dep_id]

    def _save_datasets(self, max_workers: int = 10, max_submitted: int = 64) -> None:
        """Determine which datasets to save, pool them together in groups that are being saved to the same
        parquet file, then do some concurrent save tasks.

        Args:
            max_workers: Maximum number of thread workers to initialise
            max_submitted: Maximum number of tasks to submit to the pool at once
        """

        def await_submission_slot(_submitted_tasks: list) -> None:
            """Wait for any submitted task to complete, propagate its exception, and free one slot.

            Args:
                _submitted_tasks: List of submitted tasks.
            """
            done = next(as_completed(_submitted_tasks))  # get the next finished task
            done.result()  # propagate any potential errors from this task
            _submitted_tasks.remove(done)  # remove it from the submitted tasks so that a new task can be added

        with self.metrics.time_write.time():
            # Set up a thread pool so that multiple save tasks can be executed concurrently.
            #   A bounded ThreadPoolExecutor should be suitable here because S3 writes are I/O-bound and benefit from
            #   concurrency without increasing CPU load.
            with ThreadPoolExecutor(max_workers=max_workers) as pool:
                # Keep track of number of tasks being submitted, otherwise can run into memory issues because each
                # submitted task contains everything it needs in memory and is not garbage-collected until the task
                # executes
                submitted_tasks = []

                # Loop over collection of save tasks to submit to the pool
                for task in  self._build_save_tasks():
                    task = pool.submit(self.data_writer.write, *task)
                    submitted_tasks.append(task)

                    if len(submitted_tasks) >= max_submitted:
                        await_submission_slot(submitted_tasks)

                # Tidy up remaining tasks
                for task in as_completed(submitted_tasks):
                    task.result()


    def _build_save_tasks(self):
        # Collect the datasets of each resolution - these will be datasets that are all being saved to the
        # same file, so can be grouped together in one save rather than doing individual saves.
        # TODO: May need to rethink the resolution partition here.  What if datasets had same resolution but
        #   different periodicity / time anchors etc.
        dataset_groupings = defaultdict(list)
        for ds_id, container in self.graph.datasets.items():
            if container.processing_level == ProcessingLevel.PROCESSED:
                dataset_groupings[
                    f"{container.network}-{container.source_site_identifier}-{container.resolution}"
                ].append(container)

        for dataset_group, containers in dataset_groupings.items():
            # Double check all containers have the same properties
            network, site_id, resolution, bucket = check_common_attributes(
                containers, ["network", "source_site_identifier", "resolution", "source_bucket"]
            )

            # Merge the data for all containers
            group_tf = merge_multiple_timeframes([c.data for c in containers])

            # Data saved "per day", so split the grouped data by day
            data_to_write = split_by_date(group_tf.df, group_tf.time_name)

            # Yield specific save tasks
            for data_date, df in data_to_write:
                key = (
                    f"{network}/resolution={resolution}/site={site_id}/"
                    f"date={data_date:%Y-%m-%d}/data.parquet"
                )
                yield bucket, key, df, group_tf.time_name
