"""
An orchestration class used to run aggregation.
"""

import logging

import time_stream as ts

from new_processor.models.domain_models.processing_config import ProcessingMethodConfig
from new_processor.models.domain_models.time_series_container import TimeSeriesContainer
from new_processor.operations.aggregation.aggregation_methods import AggregationMethod
from new_processor.operations.flags.flag_methods import add_initial_core_flags

logger = logging.getLogger(__name__)


class AggregationPipeline:
    """Pipeline for running Aggregation methods on a TimeSeriesContainer."""

    def run(self, container: TimeSeriesContainer, dep_container: TimeSeriesContainer) -> ts.TimeFrame:
        """Execute the aggregation workflow on the time series container.

        Args:
            container: Time series container of metadata and data for the primary dataset to process.
            dep_container: Time series container for the dataset that will be aggregated.

        Returns:
            The updated TimeFrame after aggregation.
        """
        config = self._create_aggregation_method_config(container)

        method = AggregationMethod.get(config.method)
        tf = method.run(dep_container.data, config)

        tf = self._rename_aggregation_columns(tf, container.source_column, dep_container.source_column)
        tf = add_initial_core_flags(tf)

        return tf

    @staticmethod
    def _create_aggregation_method_config(container: TimeSeriesContainer) -> ProcessingMethodConfig:
        """Create the method config for the aggregation method.

        Args:
            container: Time series container containing the metadata needed for the aggregation method.

        Returns:
            Method configuration properties
        """
        return ProcessingMethodConfig(
            method=container.method.name,
            params={"aggregation_period": ts.Period.of_iso_duration(container.periodicity)},
        )

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
