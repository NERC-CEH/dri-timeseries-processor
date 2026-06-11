import logging
from datetime import datetime

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
                tf = dep.data.select(container.source_column)
                tf.metadata["column_name"] = container.source_column
                container.data = tf

            case "load-local-copy":
                container.staged_dir = self.data_router.stage_locally(container, self.start_date, self.end_date)

            case _:
                raise ValueError(f"Unknown load method: {config.method}")

        return container
