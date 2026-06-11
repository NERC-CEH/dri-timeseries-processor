import logging

from dritimeseriesprocessor.models.domain_models.processing_config import (
    DataProcessingConfig,
    DataProcessingMethodConfig,
)
from dritimeseriesprocessor.models.domain_models.time_series_container import TimeSeriesContainer
from dritimeseriesprocessor.routers.data.data_router import DataRouter
from dritimeseriesprocessor.utils.enums import ConfigurationType, DatasetType

logger = logging.getLogger(__name__)


class LoadPipeline:
    operation_type: ConfigurationType = ConfigurationType.LOAD

    def __init__(self, data_router: DataRouter):
        self.data_router = data_router

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
                # When loading from an ObservationDataset bundle (e.g. the EddyPro output),
                # slice to just the target column and create a fresh TimeFrame via
                # init_timeframe rather than copy(). copy() shares the bundle's flag manager
                # across all containers extracting from it, causing DuplicateFlagSystemError
                # when add_initial_core_flags is called on each one independently.
                if dep.dataset_type == DatasetType.OBSERVATION_DATASET and container.source_column is not None:
                    col_df = dep.data.df.select([container.time_column_name, container.source_column])
                    container.init_timeframe(col_df)
                else:
                    container.data = dep.data.copy(share_df=False)

            case "load-local-copy":
                container.staged_dir = self.data_router.stage_locally(
                    container, config.params["processing_start_date"], config.params["processing_end_date"]
                )

            case _:
                raise ValueError(f"Unknown load method: {config.method}")

        return container
