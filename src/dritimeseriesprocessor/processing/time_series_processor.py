"""
Time series processing pipeline.

This module defines the `TimeSeriesProcessor`, which orchestrates dataset processing based on a dataset dependency
graph. It loads raw data, applies initial flagging, and carries out further processing steps according to each
dataset's method type.
"""

import logging
from collections.abc import Iterator
from datetime import date, datetime

import polars as pl

from dritimeseriesprocessor.dag.dataset_dependency_graph import DatasetDependencyGraph
from dritimeseriesprocessor.io_backend.writer import ParquetWriterInterface
from dritimeseriesprocessor.metrics.metrics import Metrics
from dritimeseriesprocessor.models.domain_models.time_series_container import (
    TimeSeriesContainer,
    check_common_attributes,
    group_containers,
)
from dritimeseriesprocessor.operations.aggregation.aggregation_pipeline import AggregationPipeline
from dritimeseriesprocessor.operations.correction.correction_pipeline import CorrectionPipeline
from dritimeseriesprocessor.operations.derivation.derivation_pipeline import DerivationPipeline
from dritimeseriesprocessor.operations.flags.flag_methods import add_initial_core_flags
from dritimeseriesprocessor.operations.infill.infill_pipeline import InfillPipeline
from dritimeseriesprocessor.operations.quality_control.qc_pipeline import QCPipeline
from dritimeseriesprocessor.routers.data.data_router import DataRouter
from dritimeseriesprocessor.utils.enums import MethodType, OperationType, ProcessingLevel
from dritimeseriesprocessor.utils.polars_utils import split_by_date
from dritimeseriesprocessor.utils.task_pool import run_threaded_tasks
from dritimeseriesprocessor.utils.time_stream_utils import merge_multiple_timeframes
from dritimeseriesprocessor.utils.timer import log_duration

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
                # Collect all the "LOAD" datasets (can remove from the graph as we will have done their processing)
                load_containers = [c for c in self.graph.datasets.values() if c.method_type() == MethodType.LOAD]
                logger.info(f"Collecting and loading [{len(load_containers)}] datasets.")
                self._batch_load_raw(*load_containers)

                # Sort the containers into an order that guarantees dependency resolution
                layers = self.graph.layered_topo_sort()
                logger.info("Processing pipeline started.")

                for layer in layers:
                    self.process_layer(layer)

                logger.info("-" * 30)
                logger.info("Collecting and saving datasets.")
                self._save_datasets()

        logger.info("Processing pipeline finished. Pushing prometheus metrics.")
        self.metrics.export_metrics_to_pushgateway()

    def process_layer(self, layer: list[str]) -> None:
        """Process an individual layer of the dependency graph.

        Args:
            layer: Datasets to process
        """
        for dataset_id in layer:
            try:
                self.process_dataset(dataset_id)
            except Exception:
                self.metrics.failed.inc()
                self.graph.datasets[dataset_id].failed = True
                logger.exception(f"Processing failed. Failed status added to container: {dataset_id}")
            else:
                self.metrics.success.inc()

    def process_dataset(self, dataset_id: str) -> None:
        """Process a single dataset according to the configured method type in its metadata.

        Args:
            dataset_id: The dataset to process.
        """

        container = self.graph.datasets[dataset_id]
        for dep_id in container.all_dependencies():
            if self.graph.datasets[dep_id].failed:
                container.failed = True
                logger.error(f"Skipping {dataset_id} - dependency {dep_id} failed")
                return

        match container.method_type():
            case MethodType.LOAD:
                # Already handled by the initial batch loading
                pass

            case MethodType.PROCESS:
                self._process(container)

            case MethodType.AGGREGATION:
                self._aggregate(container)

            case MethodType.DERIVATION:
                self._derive(container)

    @log_duration("Loading datasets time taken: ", footer=True)
    def _batch_load_raw(self, *containers: TimeSeriesContainer) -> None:
        """Load raw time-series data for multiple datasets in grouped batches.

        Containers are grouped by network, site, resolution, and source dataset so that a single query
        can retrieve all columns for each group in one read. Each container's data is then extracted from
        the combined result and initialised into a TimeFrame.

        Args:
           containers: List of the containers to load.
        """
        common_keys = ["network", "source_site_identifier", "resolution", "source_dataset"]
        groupings = group_containers(containers, common_keys)

        with self.metrics.time_load.time():
            for dataset_group, containers in groupings.items():
                try:
                    combined_df = self.data_router.query_by_date_range(
                        *containers, start_date=self.start_date, end_date=self.end_date
                    )

                    if combined_df.is_empty():
                        raise ValueError(f"No data returned for group: {dataset_group}")

                except Exception:
                    for container in containers:
                        self.metrics.no_data.inc()
                        container.failed = True
                    logger.exception(f"Failed to load data for group: {dataset_group}")
                    continue

                for container in containers:
                    col = container.source_column
                    try:
                        df = combined_df.select([container.time_column_name, col])

                        if df.is_empty():
                            raise ValueError(f"No data returned for dataset: {container.ts_id}")

                    except Exception:
                        self.metrics.no_data.inc()
                        container.failed = True
                        logger.exception(f"Failed to select columns for dataset: {container.ts_id}")
                        continue

                    container.init_timeframe(df)
                    container.data = add_initial_core_flags(container.data)

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

    @log_duration("Saving datasets time taken: ", footer=True)
    def _save_datasets(self) -> None:
        """Determine which datasets to save, pool them together in groups that are being saved to the same
        parquet file, then do some concurrent save tasks.
        """
        with self.metrics.time_write.time():
            tasks = self._build_save_tasks()
            run_threaded_tasks(tasks, self.data_writer.write)

    def _build_save_tasks(self) -> Iterator[tuple[str, str, pl.DataFrame, str]]:
        """Build save tasks for processed datasets.

        This method groups processed datasets that are written to the same Parquet output, merges their timeframes,
        splits the merged data by day, and yields arguments needed for the actual save tasks.

        Each yielded task contains all information required to perform a single write operation, but doesn't do
        the actual saving. This separation allows the caller to execute the tasks synchronously or concurrently.

        Yields:
            Tuples of the form:
                (
                    bucket (str) : The S3 bucket to write to
                    key (str) : The full S3 object key for the parquet file
                    df (pl.DataFrame) : The dataframe to be written
                    time_column_name (str) : The name of the time column in df
                )

        Using Yield to produce a generator so that we're not holding all dataframes in memory simultaneously.
        """
        common_keys = ["network", "source_site_identifier", "resolution", "source_bucket"]
        processed = tuple(
            [
                c
                for c in self.graph.datasets.values()
                if c.processing_level == ProcessingLevel.PROCESSED and not c.failed
            ]
        )
        if not processed:
            logger.warning("No datasets available to be saved.")
            return

        groupings = group_containers(processed, common_keys)

        for dataset_group, containers in groupings.items():
            # Double check all containers have the same properties
            network, site_id, resolution, bucket = check_common_attributes(containers, common_keys)

            # Merge the data for all containers
            group_tf = merge_multiple_timeframes([c.data for c in containers if c.data is not None])

            # Data saved "per day", so split the grouped data by day
            data_to_write = split_by_date(group_tf.df, group_tf.time_name)

            # Yield specific save tasks
            for data_date, df in data_to_write:
                key = f"{network}/resolution={resolution}/site={site_id}/date={data_date:%Y-%m-%d}/data.parquet"
                yield bucket, key, df, group_tf.time_name
