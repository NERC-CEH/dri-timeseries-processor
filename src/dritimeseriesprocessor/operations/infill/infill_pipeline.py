import logging

import polars as pl
import time_stream as ts

from dritimeseriesprocessor.models.domain_models.processing_config import DataProcessingMethodConfig
from dritimeseriesprocessor.operations.flags.flag_methods import update_infill_core_flags
from dritimeseriesprocessor.operations.flags.flag_names import INFILL_FLAG_SYS_NAME, infill_flag_column_name
from dritimeseriesprocessor.operations.infill.infill_methods import InfillMethod
from dritimeseriesprocessor.operations.operation_pipeline import OperationPipeline
from dritimeseriesprocessor.utils.enums import ConfigurationType

logger = logging.getLogger(__name__)


class InfillPipeline(OperationPipeline):
    """Processor for running infilling on a TimeSeriesContainer."""

    def __init__(self):
        super().__init__(ConfigurationType.INFILLING, INFILL_FLAG_SYS_NAME)

    def apply(self, tf: ts.TimeFrame, config: DataProcessingMethodConfig, dataset_repository: dict) -> ts.TimeFrame:
        """Apply the given infill method to the TimeFrame data.

        Args:
            tf: Time series frame to infill.
            config: Configuration of the infill method.
            dataset_repository: Repository for accessing additional datasets.

        Returns:
            Result of applying the infill method.
        """

        # Collect any dependency TimeFrame to run infill with
        if "dep_ts" in config.params:
            dep_tf = dataset_repository[config.params["dep_ts"]].data
            config.params["alt_df"] = dep_tf.df
            config.params["alt_data_column"] = dep_tf.metadata["column_name"]

        method = InfillMethod.get(config.method)
        result = method.run(tf, config)
        self._add_flag(tf, result, tf.metadata["column_name"], config.method)
        return result

    def get_flag_column(self, column: str) -> str:
        """Determine the infill flag column name for a given data column.

        Args:
            column: Name of the data column.

        Returns:
            Name of the corresponding infill flag column.
        """
        return infill_flag_column_name(column)

    def compute_flag_mask(self, tf: ts.TimeFrame, result: ts.TimeFrame, column_name: str) -> pl.Series:
        """Return an object that can be used to determine the mask for adding a flag to the flag column.

        For infill, the flag mask compares the original with the result and provides True where there are differences.

        Args:
            tf: Original TimeFrame being processed.
            result: Result from applying infilling to tf.
            column_name: Name of the column being processed.

        Returns:
            Boolean series where data has changed after infilling.
        """
        before = tf.df[column_name]
        after = result.df[column_name]

        before_is_null = before.is_null() | before.is_nan()
        after_is_null = after.is_null() | after.is_nan()

        return before_is_null.ne(after_is_null)

    def core_flag_updater(self, tf: ts.TimeFrame) -> ts.TimeFrame:
        """Update core flags with the infill flag after all methods are applied.

        Args:
            tf: TimeFrame with flags to update.

        Returns:
            Timeframe with updated core flags
        """
        return update_infill_core_flags(tf)
