"""
An orchestration class used to run for processing operations for corrections, quality control and infilling.
"""

import logging
from abc import ABC, abstractmethod

import polars as pl
import time_stream as ts

from dritimeseriesprocessor.models.domain_models.processing_config import (
    DataProcessingConfig,
    DataProcessingMethodConfig,
)
from dritimeseriesprocessor.models.domain_models.time_series_container import TimeSeriesContainer
from dritimeseriesprocessor.operations.aggregation.aggregation_methods import AggregationMethod
from dritimeseriesprocessor.operations.correction.correction_methods import CorrectionMethod
from dritimeseriesprocessor.operations.derivation.derivation_methods import DerivationMethod
from dritimeseriesprocessor.operations.infill.infill_methods import InfillMethod
from dritimeseriesprocessor.operations.quality_control.qc_methods import QcMethod
from dritimeseriesprocessor.utils.enums import ConfigurationType

logger = logging.getLogger(__name__)


OPERATION_METHOD_REGISTRY = {
    ConfigurationType.CORRECTION: CorrectionMethod._REGISTRY,
    ConfigurationType.QUALITY_CONTROL: QcMethod._REGISTRY,
    ConfigurationType.INFILLING: InfillMethod._REGISTRY,
    ConfigurationType.AGGREGATION: AggregationMethod._REGISTRY,
    ConfigurationType.DERIVATION: DerivationMethod._REGISTRY,
}


class OperationPipeline(ABC):
    """A base class to define the workflow of operations such as corrections, QC, and infilling.

    Subclasses implement the operation specific components such as applying a method, computing flag masks,
    sorting configuration blocks, and constructing flag column names.
    """

    def __init__(self, operation_type: ConfigurationType):
        """Initialise the operation processor.

        Args:
            operation_type: Type of operation.
        """
        self.operation_type = operation_type
        self.registry = OPERATION_METHOD_REGISTRY[self.operation_type]

    @abstractmethod
    def apply(
        self, tf: ts.TimeFrame, config: DataProcessingMethodConfig, dataset_repository: dict[str, TimeSeriesContainer]
    ) -> ts.TimeFrame:
        """Apply a specific method to the time series data.

        Args:
            tf: Time series frame to process.
            config: Configuration that the method requires.
            dataset_repository: Repository for accessing additional datasets.

        Returns:
            Result of applying the method, format depends on implementation.
        """
        pass

    @abstractmethod
    def get_flag_column(self, column: str) -> str:
        """Determine the flag column name for a given data column.

        Args:
            column: Name of the data column.

        Returns:
            Name of the corresponding flag column.
        """
        pass

    @abstractmethod
    def compute_flag_mask(self, tf: ts.TimeFrame, result: ts.TimeFrame, column_name: str) -> pl.Series | pl.Expr:
        """Compute a boolean mask indicating which values should be flagged.

        Args:
            tf: Original TimeFrame being processed.
            result: Result from applying a method to tf.
            column_name: Name of the column being processed.

        Returns:
            Boolean mask suitable as use in a Polars expression for flagging.
        """
        pass

    @abstractmethod
    def core_flag_updater(self, tf: ts.TimeFrame) -> ts.TimeFrame:
        """Update core flags after all methods are applied.

        Args:
            tf: TimeFrame with flags to update.

        Returns:
            Timeframe with updated core flags
        """
        pass

    def run(
        self,
        container: TimeSeriesContainer,
        dataset_repository: dict[str, TimeSeriesContainer],
        config: DataProcessingConfig,
    ) -> ts.TimeFrame:
        """Execute the full operation workflow on the time series container.

        Args:
            container: Time series container of metadata and data for the primary dataset to process.
            dataset_repository: Repository for accessing additional datasets.
            config: The data processing configuration to run.

        Returns:
            The updated TimeFrame after all operations and flag updates.
        """
        tf = container.data

        # Apply configs
        for cfg in config.method_configs:
            logger.info(f"Operation: {self.operation_type} | {cfg.method}")

            # Run the method
            tf = self.apply(tf=tf, config=cfg, dataset_repository=dataset_repository)  # type: ignore[arg-type]
            tf = self.apply_rounding(tf, cfg)

        # Update core flags
        tf = self.core_flag_updater(tf)  # type: ignore[arg-type] - we know tf will exist at this point

        # Ensure time column name of tf is same as container's (not set for ObservationDatasets)
        if container.time_column_name is not None:
            tf = tf.rename_time_column(container.time_column_name)

        return tf

    def _add_flag(self, tf: ts.TimeFrame, result: ts.TimeFrame, col_name: str, flag_name: str) -> None:
        """Apply a flag to the flag column

        Args:
            tf: TimeFrame containing original data.
            result: The result of the operation.
            col_name: Name of the parent column.
            flag_name: Type of flag to apply (must exist in the associated flag system).
        """
        flag_column = self.get_flag_column(col_name)
        mask = self.compute_flag_mask(tf, result, col_name)
        if mask is not None:
            result.add_flag(flag_column, flag_name, mask)

    @staticmethod
    def apply_rounding(tf: ts.TimeFrame, config: DataProcessingMethodConfig) -> ts.TimeFrame:
        """Apply any rounding to the resulting TimeFrame data (if required by metadata)

        Args:
            tf: TimeFrame containing data to round.
            config: Configuration options containing round parameter.

        Returns:
            TimeFrame with rounded data.
        """
        round_decimals: int | None = config.params.get("round")
        if round_decimals is None:
            return tf

        col_name = tf.metadata["column_name"]
        return tf.with_df(tf.df.with_columns(pl.col(col_name).round(round_decimals).alias(col_name)))
