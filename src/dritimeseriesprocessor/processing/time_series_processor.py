"""
Time series processing pipeline.

This module defines the `TimeSeriesProcessor`, which orchestrates dataset processing based on a dataset dependency
graph. It loads raw data, applies initial flagging, and carries out further processing steps according to each
dataset's method type.
"""

import logging
from collections.abc import Iterator
from datetime import datetime

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
from dritimeseriesprocessor.operations.flags.flag_methods import add_initial_core_flags, initialise_flag_systems
from dritimeseriesprocessor.operations.infill.infill_pipeline import InfillPipeline
from dritimeseriesprocessor.operations.load.load_pipeline import LoadPipeline
from dritimeseriesprocessor.operations.quality_control.qc_pipeline import QCPipeline
from dritimeseriesprocessor.routers.data.data_router import DataRouter
from dritimeseriesprocessor.utils.enums import (
    ConfigurationType,
    DatasetType,
    ProcessingLevel,
)
from dritimeseriesprocessor.utils.polars_utils import split_by_date
from dritimeseriesprocessor.utils.task_pool import run_threaded_tasks
from dritimeseriesprocessor.utils.time_stream_utils import merge_multiple_timeframes
from dritimeseriesprocessor.utils.timer import log_duration
from dritimeseriesprocessor.utils.urls import SITE_URI

logger = logging.getLogger(__name__)


class TimeSeriesProcessor:
    """Orchestrates the dataset processing pipeline.

    The processor traverses the graph in topological layers and processes each dataset in turn.
    """

    def __init__(
        self,
        graph: DatasetDependencyGraph,
        data_router: DataRouter,
        data_writer: ParquetWriterInterface,
        start_date: datetime,
        end_date: datetime,
        metrics: Metrics,
    ):
        """Initialise the processor.

        Args:
            graph: Dependency graph containing dataset relationships and repository of dataset containers.
            data_router: Router for retrieving data from storage.
            data_writer: Handles writing data to parquet files.
            start_date: Start of the date range to process (inclusive).
            end_date: End of the date range to process (inclusive).
            metrics: Metrics reporter.
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
        try:
            with self.metrics.time_pipeline.time():
                if not self.graph.datasets:
                    logger.error("No datasets found in dependency graph.")
                else:
                    # Load data for all 'load' containers
                    self._batch_load()

                    layers = self.graph.layered_topo_sort()
                    logger.info("Processing pipeline started.")

                    for layer in layers:
                        self.process_layer(layer)

                    logger.info("-" * 30)
                    logger.info("Collecting and saving datasets.")
                    self._save_datasets()

            logger.info("Processing pipeline finished. Pushing prometheus metrics.")
            self.metrics.export_metrics_to_pushgateway()
        finally:
            self.data_router.cleanup()

    def process_layer(self, layer: list[str]) -> None:
        """Process an individual layer of the dependency graph.

        Args:
            layer: Datasets to process
        """
        for dataset_id in layer:
            if self.graph.datasets[dataset_id].load_only:
                logger.info(f"Skipping load-only dataset: {dataset_id}")
                continue
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
        if container.is_load():
            # A "load" container has no processing configs - it is a raw dataset whose data was already
            # fetched up-front by _batch_load(), so there is nothing to process here.
            # This is different from the ConfigurationType.LOAD step below, which runs an explicit method as part of
            # a container that *does* have a processing plan and processing configs. This runs methods in the
            # LoadPipeline that do things like stage local copies, or moves data from one container to another.
            return

        logger.info(f"Processing dataset: {dataset_id}")

        for dep_id in container.all_dependencies():
            if self.graph.datasets[dep_id].failed:
                container.failed = True
                logger.error(f"Skipping {dataset_id} - dependency {dep_id} failed")
                return

        for idx, plan_id in enumerate(container.plan_order):
            config = container.data_processing_configs[plan_id]

            match config.config_type:
                case ConfigurationType.LOAD:
                    container = LoadPipeline(self.data_router, self.start_date, self.end_date).run(
                        container, self.graph.datasets, config
                    )
                    # LOAD brings in raw data: we need to register any flag systems, create the flag columns the
                    # dataset declares, and set every row's core flag as "unchecked"
                    initialise_flag_systems(container, self.graph.flagging_systems)
                    add_initial_core_flags(container)

                case ConfigurationType.CORRECTION:
                    container.data = CorrectionPipeline(self.graph.flagging_systems).run(
                        container, self.graph.datasets, config
                    )

                case ConfigurationType.QUALITY_CONTROL:
                    # Only remove flagged data after the last QC block - sequential QC blocks must
                    # accumulate flags across all their checks before any data is nulled out.
                    is_final_qc = self._get_next_step_type(container, idx) != ConfigurationType.QUALITY_CONTROL
                    container.data = QCPipeline(self.graph.flagging_systems).run(
                        container, self.graph.datasets, config, remove_flagged=is_final_qc
                    )

                case ConfigurationType.INFILLING:
                    container.data = InfillPipeline(self.graph.flagging_systems).run(
                        container, self.graph.datasets, config
                    )

                case ConfigurationType.AGGREGATION:
                    container.data = AggregationPipeline(self.graph.flagging_systems).run(
                        container, self.graph.datasets, config
                    )

                case ConfigurationType.DERIVATION:
                    site_metadata = self.graph.site_metadata[f"{SITE_URI}/{container.source_site}"]
                    for cfg in config.method_configs:
                        cfg.params["processing_start_date"] = self.start_date.date()
                        cfg.params["processing_end_date"] = self.end_date.date()
                    container.data = DerivationPipeline(site_metadata, self.graph.flagging_systems).run(
                        container, self.graph.datasets, config
                    )

    @staticmethod
    def _get_next_step_type(container: TimeSeriesContainer, current_idx: int) -> ConfigurationType | None:
        """Return the config type of the next step in the plan, or None if there is no next step.

        Args:
            container: The container whose plan is being iterated.
            current_idx: Index of the current step in `container.plan_order`.

        Returns:
            The `ConfigurationType` of the next step, or None if the current step is the last.
        """
        next_idx = current_idx + 1
        if next_idx >= len(container.plan_order):
            return None
        return container.data_processing_configs[container.plan_order[next_idx]].config_type

    @log_duration("Loading datasets time taken: ", footer=True)
    def _batch_load(self) -> None:
        """Load time-series data for multiple datasets in grouped batches.

        Containers are grouped by network, site, resolution, and source dataset so that a single query
        can retrieve all columns for each group in one read. Each container's data is then extracted from
        the combined result and initialised into a TimeFrame.
        """
        containers = [c for c in self.graph.datasets.values() if c.is_load()]
        logger.info(f"Collecting and loading [{len(containers)}] datasets.")
        common_keys = ["network", "source_site_identifier", "resolution", "source_dataset", "processing_level"]
        groupings = group_containers(containers, common_keys)

        with self.metrics.time_load.time():
            for dataset_group, containers_in_group in groupings.items():
                try:
                    combined_df = self.data_router.query_by_date_range(
                        *containers_in_group, start_date=self.start_date, end_date=self.end_date
                    )

                    if combined_df.is_empty():
                        raise ValueError(f"No data returned for group: {dataset_group}")

                except Exception:
                    for container in containers_in_group:
                        self.metrics.no_data.inc()
                        container.failed = True
                    logger.exception(f"Failed to load data for group: {dataset_group}")
                    continue

                for container in containers_in_group:
                    col = container.source_column
                    try:
                        df = combined_df.select([container.time_column_name, col])
                        container.init_timeframe(df)

                        if container.data is None:
                            raise ValueError(f"No data returned for dataset: {container.ts_id}")

                    except Exception:
                        self.metrics.no_data.inc()
                        container.failed = True
                        logger.exception(f"Failed to select columns for dataset: {container.ts_id}")
                        continue

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
            c
            for c in self.graph.datasets.values()
            if c.processing_level == ProcessingLevel.PROCESSED
            and not c.failed
            and c.data is not None
            and not c.load_only
            and c.dataset_type != DatasetType.OBSERVATION_DATASET
        )
        if not processed:
            logger.warning("No datasets available to be saved.")
            return

        groupings = group_containers(processed, common_keys)

        for _, containers in groupings.items():
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
