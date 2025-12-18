"""
Time series processing pipeline.

This module defines the `TimeSeriesProcessor`, which orchestrates dataset processing based on a dataset dependency
graph. It loads raw data, applies initial flagging, and carries out further processing steps according to each
dataset's method type.
"""

import logging
from datetime import date, datetime

from time_stream import TimeFrame

from new_processor.dag.dataset_dependency_graph import DatasetDependencyGraph
from new_processor.io_backend.writer import ParquetWriterInterface
from new_processor.metrics.metrics import Metrics
from new_processor.models.domain_models.time_series_container import TimeSeriesContainer
from new_processor.operations.aggregation.aggregation_pipeline import AggregationPipeline
from new_processor.operations.correction.correction_pipeline import CorrectionPipeline
from new_processor.operations.derivation.derivation_pipeline import DerivationPipeline
from new_processor.operations.flags.flag_methods import add_initial_core_flags
from new_processor.operations.infill.infill_pipeline import InfillPipeline
from new_processor.operations.quality_control.qc_pipeline import QCPipeline
from new_processor.routers.data.data_router import DataRouter
from new_processor.utils.enums import MethodType, OperationType
from new_processor.utils.polars_utils import split_by_date

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

        match container.method.method_type:
            case MethodType.LOAD:
                self._load_raw(container)

            case MethodType.PROCESS:
                self._process(container)
                self._save(container)

            case MethodType.AGGREGATION:
                self._aggregate(container)
                self._save(container)

            case MethodType.DERIVATION:
                self._derive(container)
                self._save(container)

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
                tf = TimeFrame(
                    df=df,
                    time_name=container.time_column_name,
                    resolution=container.resolution,
                    periodicity=container.periodicity,
                ).with_metadata({"column_name": container.source_column})

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
            dep_container = self._get_single_dependency(container)
            pipeline = OPERATION_PIPELINES[OperationType.AGGREGATION]
            container.data = pipeline.run(container, dep_container)

    def _derive(self, container: TimeSeriesContainer) -> None:
        """Run derivation to create a single dataset according to the method configurations attached via metadata.

        Args:
            container: Time series container of metadata and data for dataset to create via derivation.
        """
        logger.info(f"{MethodType.DERIVATION}: {container.ts_id}")

        with self.metrics.time_derive.time():
            pipeline = OPERATION_PIPELINES[OperationType.DERIVATION]
            container.data = pipeline.run(container, self.graph.datasets)

    def _save(self, container: TimeSeriesContainer) -> None:
        """Save the processed data within the given container.

        Args:
            container: Time series container of metadata and data for dataset to save.
        """
        with self.metrics.time_write.time():
            data_to_write = split_by_date(container.data.df, container.time_column_name)
            for data_date, df in data_to_write:
                key = (
                    f"network={container.network}/"
                    f"date={data_date.strftime('%Y-%m-%d')}/"
                    f"site={container.source_site_identifier}/"
                    f"resolution={container.resolution}/"
                    f"data.parquet"
                )
                self.data_writer.write(container.source_bucket, key, df, container.time_column_name)

    def _get_single_dependency(self, container: TimeSeriesContainer) -> TimeSeriesContainer:
        """Get the dependent time series container of the given container where it is assumed that there is only
        a single dependency.

        Args:
            container: Time series container for the dataset to fetch single dependency

        Returns:
            Dependent time series container.
        """
        num_dependents = len(container.direct_depends_on)
        if num_dependents != 1:
            raise ValueError(f"Expected a single dependent dataset. Found: {num_dependents}")

        dep_id = container.direct_depends_on[0]
        return self.graph.datasets[dep_id]
