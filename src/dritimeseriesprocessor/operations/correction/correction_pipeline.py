import logging

import polars as pl
import time_stream as ts

from dritimeseriesprocessor.models.domain_models.processing_config import DataProcessingMethodConfig
from dritimeseriesprocessor.operations.correction.correction_methods import CorrectionMethod
from dritimeseriesprocessor.operations.flags.flag_methods import update_corrections_core_flags
from dritimeseriesprocessor.operations.flags.flag_names import corrs_flag_column_name
from dritimeseriesprocessor.operations.operation_pipeline import OperationPipeline
from dritimeseriesprocessor.utils.enums import ConfigurationType

logger = logging.getLogger(__name__)


class CorrectionPipeline(OperationPipeline):
    """Processor for running corrections on a TimeSeriesContainer."""

    def __init__(self):
        super().__init__(ConfigurationType.CORRECTION)

    def apply(self, tf: ts.TimeFrame, config: DataProcessingMethodConfig, dataset_repository: dict) -> ts.TimeFrame:
        """Apply the given correction method to the TimeFrame data.

        Args:
            tf: Time series frame to correct.
            config: Configuration of the correction method.
            dataset_repository: Repository for accessing additional datasets.

        Returns:
            Result of applying the correction method.
        """
        params = config.params

        # Name any dependent timeseries with their column names
        dep_ids = config.params.get("dep_ts", [])
        if isinstance(dep_ids, str):
            dep_ids = [dep_ids]

        for dep_id in dep_ids:
            dep_tf = dataset_repository[dep_id].data
            dep_name = dep_tf.metadata["column_name"].lower()
            params[dep_name] = dep_tf

        method = CorrectionMethod.get(config.method)
        result = method.run(tf, config)
        self._add_flag(tf, result, tf.metadata["column_name"], config.method)
        return result

    def get_flag_column(self, column: str) -> str:
        """Determine the correction flag column name for a given data column.

        Args:
            column: Name of the data column.

        Returns:
            Name of the corresponding correction flag column.
        """
        return corrs_flag_column_name(column)

    def compute_flag_mask(self, tf: ts.TimeFrame, result: ts.TimeFrame, column_name: str) -> pl.Series:
        """Return an object that can be used to determine the mask for adding a flag to the flag column.

        For corrections, the flag mask compares the original with the result and provides True where
        there are differences.

        Args:
            tf: Original TimeFrame being processed.
            result: Result from applying corrections to tf.
            column_name: Name of the column being processed.

        Returns:
            Boolean series where data has changed after correcting.
        """
        before = tf.df[column_name]
        after = result.df[column_name]

        before_is_null = before.is_null() | before.is_nan()
        after_is_null = after.is_null() | after.is_nan()

        # Null status changed (null -> value or value -> null)
        null_status_changed = (before_is_null & ~after_is_null) | (~before_is_null & after_is_null)

        # Both have values but values are different
        values_changed = (~before_is_null & ~after_is_null) & (before != after)

        return null_status_changed | values_changed

    def core_flag_updater(self, tf: ts.TimeFrame) -> ts.TimeFrame:
        """Update core flags with the correction flag after all methods are applied.

        Args:
            tf: TimeFrame with flags to update.

        Returns:
            Timeframe with updated core flags
        """
        return update_corrections_core_flags(tf)
