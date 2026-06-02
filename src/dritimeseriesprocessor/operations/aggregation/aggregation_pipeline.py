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
from dritimeseriesprocessor.operations.flags.flag_names import core_flag_column_name
from dritimeseriesprocessor.operations.operation_pipeline import OperationPipeline
from dritimeseriesprocessor.utils.enums import OperationType

logger = logging.getLogger(__name__)


class AggregationPipeline(OperationPipeline):
    """Pipeline for running Aggregation methods on a TimeSeriesContainer."""

    def __init__(self):
        super().__init__(OperationType.AGGREGATION)

    def run(self, *args, **kwargs) -> ts.TimeFrame:
        """Override the parent run method, as we need to remove any invalid aggregation data and do some column
        manipulation after the pipeline has finished
        """
        tf = super().run(*args, **kwargs)
        tf = self._remove_data(tf)
        tf = self._select_columns(tf)
        return tf

    def apply(self, config: DataProcessingMethodConfig, dataset_repository: dict, *_, **__) -> ts.TimeFrame:
        """Apply the given aggregation method to the TimeFrame data.

        Args:
            _: Unused TimeFrame argument passed from parent class
            config: Configuration of the aggregation method.
            dataset_repository: Repository for accessing additional datasets.

        Returns:
            Result of applying the aggregation method.
        """

        # Collect the dependency TimeFrame to run aggregation on
        dep_container = dataset_repository[config.params["dep_ts"]]

        method = AggregationMethod.get(config.method)
        agg_tf = method.run(dep_container.data, config)
        agg_tf = self._rename_aggregation_columns(agg_tf, agg_tf.metadata["column_name"], dep_container.source_column)
        agg_tf = add_initial_core_flags(agg_tf, init_unchecked=False, init_missing=False)
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
        if container.periodicity is None:
            raise ValueError(f"No periodicity found for: {container.ts_id}")

        method_config = container.method_config
        for config in container.method_config.method_configs:
            config.params["aggregation_period"] = ts.Period.of_iso_duration(container.periodicity)

        return {method_config}

    def get_flag_column(self, column: str) -> str:
        """Not used by aggregation - flags are not applied."""
        raise NotImplementedError

    def compute_flag_mask(self, tf: ts.TimeFrame, result: ts.TimeFrame, column_name: str) -> pl.Series:
        """Not used by aggregation - flags are not applied."""
        raise NotImplementedError

    def core_flag_updater(self, tf: ts.TimeFrame) -> ts.TimeFrame:
        """Update core flags after aggregation method has been applied.

        Args:
            tf: TimeFrame with flags to update.

        Returns:
            Timeframe with updated core flags
        """
        col_name = tf.metadata["column_name"]
        core_flag_col_name = core_flag_column_name(col_name)
        actual_count_col_name = f"count_{col_name}"
        expected_count_col_name = f"expected_count_{tf.time_name}"
        valid_col_name = f"valid_{col_name}"

        # Not all values present, but above threshold values present: Data stays, flagged as "estimate"
        expr = (pl.col(actual_count_col_name) != pl.col(expected_count_col_name)) & pl.col(valid_col_name)
        tf.add_flag(core_flag_col_name, "estimated", expr)

        # Not enough values present: Data removed, flagged as "removed".
        expr = (pl.col(actual_count_col_name) != pl.col(expected_count_col_name)) & ~pl.col(valid_col_name)
        tf.add_flag(core_flag_col_name, "removed", expr)

        # No values present: No data, flagged as "missing".
        expr = pl.col(actual_count_col_name) == 0
        tf.add_flag(core_flag_col_name, "missing", expr)

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

    @staticmethod
    def _remove_data(tf: ts.TimeFrame) -> ts.TimeFrame:
        """Remove data from any rows that failed the aggregation threshold check

        Args:
            tf: TimeFrame to remove data from

        Returns:
            TimeFrame with bad data removed
        """
        col_name = tf.metadata["column_name"]
        valid_col_name = f"valid_{col_name}"

        return tf.with_df(
            tf.df.with_columns(
                pl.when(~pl.col(valid_col_name))
                .then(None)
                .otherwise(pl.col(col_name))
                .cast(tf.df[col_name].dtype)
                .alias(col_name)
            )
        )

    @staticmethod
    def _select_columns(tf: ts.TimeFrame) -> ts.TimeFrame:
        """Final selection of the required aggregation column from the TimeFrame

        Args:
            tf: TimeFrame to select columns from

        Returns:
            TimeFrame with selected columns
        """
        col_name = tf.metadata["column_name"]
        core_col = core_flag_column_name(col_name)
        cols = [col_name]
        if core_col in tf.flag_columns:
            cols.append(core_col)
        return tf.select(cols)
