import logging
from datetime import datetime

import time_stream as ts

from dritimeseriesprocessor.models.domain_models.processing_config import (
    DataProcessingConfig,
    DataProcessingMethodConfig,
)
from dritimeseriesprocessor.models.domain_models.time_series_container import TimeSeriesContainer
from dritimeseriesprocessor.routers.data.data_router import DataRouter
from dritimeseriesprocessor.utils.enums import ConfigurationType

logger = logging.getLogger(__name__)


class LoadPipeline:
    operation_type: ConfigurationType = ConfigurationType.LOAD

    def __init__(self, data_router: DataRouter, start_date: datetime, end_date: datetime):
        self.data_router = data_router
        self.start_date = start_date
        self.end_date = end_date

    def run(
        self,
        container: TimeSeriesContainer,
        dataset_repository: dict[str, TimeSeriesContainer],
        config: DataProcessingConfig,
    ) -> TimeSeriesContainer:

        # Apply configs
        for cfg in config.method_configs:
            logger.info(f"Operation: {self.operation_type} | {cfg.method}")

            # Run the method
            container = self.apply(container=container, config=cfg, dataset_repository=dataset_repository)

        return container

    def apply(
        self, container: TimeSeriesContainer, config: DataProcessingMethodConfig, dataset_repository: dict
    ) -> TimeSeriesContainer:
        """Apply the given load method

        Args:
            container: Container with instructions to load
            config: Configuration of the load method.
            dataset_repository: Repository for accessing additional datasets.
        """

        match config.method:
            case "load":
                # Collect the dependency dataset to load into this container
                dep = dataset_repository[config.params["dep_ts"]]
                if dep.data is None:
                    raise RuntimeError(f"No data found for base dependency: {dep.ts_id}")
                if container.source_column is None:
                    raise ValueError(f"No source column name for dataset: {container.ts_id}")
                tf = self._select_dependency_column(dep.data, dep.source_column, container.source_column)
                tf.metadata["column_name"] = container.source_column
                tf.metadata["unit"] = container.unit
                # The source bundle may have a different time_anchor than this container
                # (e.g. an ObservationDataset bundle has no measure so defaults to "start",
                # while the extracted time-series dataset declares its own anchor via metadata).
                if container.time_anchor and container.time_anchor != tf.time_anchor:
                    tf = ts.TimeFrame(
                        tf.df,
                        tf.time_name,
                        resolution=tf.resolution,
                        periodicity=tf.periodicity,
                        time_anchor=container.time_anchor,
                    )
                    tf.metadata["column_name"] = container.source_column
                    tf.metadata["unit"] = container.unit
                container.data = tf

            case "load-local-copy":
                container.staged_dir = self.data_router.stage_locally(container, self.start_date, self.end_date)

            case _:
                raise ValueError(f"Unknown load method: {config.method}")

        return container

    @staticmethod
    def _select_dependency_column(dep_data: ts.TimeFrame, dep_column: str | None, target_column: str) -> ts.TimeFrame:
        """Take the dependency's data column and rename it to the target dataset's column name.

        A processed dataset can name its column differently from the raw dataset it loads from. A dependency with no
        column of its own (e.g. in a multi-column bundle) is read by the target dataset's column name instead.

        Args:
            dep_data: The dependency's data.
            dep_column: The dependency's column name, or None for a bundle.
            target_column: The column name of the dataset being loaded into.

        Returns:
            A TimeFrame holding just the selected column, under the target dataset's column name.
        """
        column_to_read = dep_column or target_column
        tf = dep_data.select(column_to_read)
        return tf.with_df(tf.df.rename({column_to_read: target_column}))
