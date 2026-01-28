"""
An orchestration class used to run aggregation.
"""

import logging

import polars as pl
import time_stream as ts

from dritimeseriesprocessor.models.domain_models.processing_config import (
    DataProcessingConfig,
    DataProcessingMethodConfig,
)
from dritimeseriesprocessor.models.domain_models.time_series_container import TimeSeriesContainer
from dritimeseriesprocessor.operations.aggregation.aggregation_methods import AggregationMethod
from dritimeseriesprocessor.operations.flags.flag_methods import add_initial_core_flags
from dritimeseriesprocessor.operations.operation_pipeline import OperationPipeline
from dritimeseriesprocessor.utils.enums import OperationType

logger = logging.getLogger(__name__)


class AggregationPipeline(OperationPipeline):
    """Pipeline for running Aggregation methods on a TimeSeriesContainer."""

    def __init__(self):
        super().__init__(OperationType.AGGREGATION)

    def apply(self, tf: ts.TimeFrame, config: DataProcessingMethodConfig, dataset_repository: dict) -> ts.TimeFrame:
        """Apply the given aggregation method to the TimeFrame data.

        Args:
            tf: Time series frame to aggregate.
            config: Configuration of the aggregation method.
            dataset_repository: Repository for accessing additional datasets.

        Returns:
            Result of applying the aggregation method.
        """

        # Collect the dependency TimeFrame to run aggregation on
        dep_container = dataset_repository[config.params["dep_ts"]]

        method = AggregationMethod.get(config.method)
        agg_tf = method.run(dep_container.data, config)
        agg_tf = self._rename_aggregation_columns(agg_tf, tf.metadata["column_name"], dep_container.source_column)
        agg_tf = add_initial_core_flags(agg_tf, init_unchecked=False)
        return agg_tf

    def get_configs(self, container: TimeSeriesContainer) -> set[DataProcessingConfig]:
        """Extract the aggregation method configuration.

        Args:
            container: Time series container to get the aggregate method configurations from.

        Returns:
            Aggregation configurations to be applied.
        """
        if container.method_config is None:
            raise ValueError(f"No aggregation config found for: {container.ts_id}")
        return {container.method_config}

    def get_flag_column(self, column: str) -> str:
        """Not required for aggregation method."""
        pass

    def compute_flag_mask(self, tf: ts.TimeFrame, result: ts.TimeFrame, column_name: str) -> pl.Series:
        """Not required for aggregation method."""
        pass

    def core_flag_updater(self, tf: ts.TimeFrame) -> ts.TimeFrame:
        """Not yet implemented for aggregation method."""
        return tf

    @staticmethod
    def _rename_aggregation_columns(tf: ts.TimeFrame, parent_col: str, dep_col: str) -> ts.TimeFrame:
        """Renames the columns of the output aggregation TimeFrame

        Args:
            tf: The TimeFrame of aggregation results
            parent_col: The name of the parent column (what we want to rename to)
            dep_col: The name of the column that was aggregated

        Returns:
            TimeFrame with renamed columns
        """
        tf = tf.with_df(tf.df.rename({dep_col: parent_col}))
        tf.metadata["column_name"] = parent_col
        return tf
