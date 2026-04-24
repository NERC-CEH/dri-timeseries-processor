"""
An orchestration class used to run derivations.
"""

import logging

import polars as pl
import time_stream as ts

from dritimeseriesprocessor.models.domain_models.processing_config import (
    DataProcessingConfig,
    DataProcessingMethodConfig,
)
from dritimeseriesprocessor.models.domain_models.time_series_container import TimeSeriesContainer
from dritimeseriesprocessor.operations.derivation.derivation_methods import DerivationMethod
from dritimeseriesprocessor.operations.flags.flag_methods import add_initial_core_flags
from dritimeseriesprocessor.operations.operation_pipeline import OperationPipeline
from dritimeseriesprocessor.utils.enums import OperationType

logger = logging.getLogger(__name__)


class DerivationPipeline(OperationPipeline):
    """Pipeline for running Derivation methods on a TimeSeriesContainer."""

    def __init__(self):
        super().__init__(OperationType.DERIVATION)

    def apply(self, tf: ts.TimeFrame, config: DataProcessingMethodConfig, dataset_repository: dict) -> ts.TimeFrame:
        """Apply the given derivation method to the TimeFrame data.

        Args:
            tf: Time series frame to derive.
            config: Configuration of the derivation method.
            dataset_repository: Repository for accessing additional datasets.

        Returns:
            Result of applying the derivation method.
        """

        dep_ts_values = []
        if "dep_ts" in config.params:
            dep_ts_values = config.params["dep_ts"]
        elif "load_dep_ts" in config.params:
            dep_ts_values = config.params["load_dep_ts"]

        if dep_ts_values is None:
            dep_ts_list = []
        elif isinstance(dep_ts_values, str):
            dep_ts_list = [dep_ts_values]
        else:
            dep_ts_list = dep_ts_values

        for dep_ts_id in dep_ts_list:
            dep_container = dataset_repository[dep_ts_id]
            config.params[dep_container.source_column.lower()] = dep_container.data

        method = DerivationMethod.get(config.method)
        tf = method.run(config)
        tf = add_initial_core_flags(tf, init_unchecked=False)

        return tf

    def get_configs(self, container: TimeSeriesContainer) -> set[DataProcessingConfig]:
        """Extract the derivation method configuration.

        Args:
            container: Time series container to get the derivation method configurations from.

        Returns:
            Derivation configurations to be applied.
        """
        if container.method_config is None:
            raise ValueError(f"No derivation config found for: {container.ts_id}")

        for cfg in container.method_config.method_configs:
            cfg.params["output_col"] = container.source_column
            cfg.params["resolution"] = container.resolution
            cfg.params["periodicity"] = container.periodicity

        return {container.method_config}

    def get_flag_column(self, column: str) -> str:
        """Not required for aggregation method."""
        pass

    def compute_flag_mask(self, tf: ts.TimeFrame, result: ts.TimeFrame, column_name: str) -> pl.Series:
        """Not required for aggregation method."""
        pass

    def core_flag_updater(self, tf: ts.TimeFrame) -> ts.TimeFrame:
        """Not yet implemented for derivation method."""
        return tf
