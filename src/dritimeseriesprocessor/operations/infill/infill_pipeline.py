import logging

import polars as pl
import time_stream as ts

from dritimeseriesprocessor.models.domain_models.processing_config import DataProcessingMethodConfig
from dritimeseriesprocessor.operations.flags.flag_methods import update_infill_core_flags
from dritimeseriesprocessor.operations.infill.infill_methods import InfillMethod
from dritimeseriesprocessor.operations.operation_pipeline import OperationPipeline
from dritimeseriesprocessor.utils.enums import ConfigurationType, FlagRole

logger = logging.getLogger(__name__)


class InfillPipeline(OperationPipeline):
    """Processor for running infilling on a TimeSeriesContainer."""

    flag_role = FlagRole.INFILL

    def __init__(self, flag_systems: dict[str, dict[str, int]]):
        super().__init__(ConfigurationType.INFILLING, flag_systems)

    def apply(
        self, tf: ts.TimeFrame | None, config: DataProcessingMethodConfig, dataset_repository: dict
    ) -> ts.TimeFrame:
        """Apply the given infill method to the TimeFrame data.

        Args:
            tf: Time series frame to infill.
            config: Configuration of the infill method.
            dataset_repository: Repository for accessing additional datasets.

        Returns:
            Result of applying the infill method.
        """
        if tf is None:
            raise ValueError(f"Infill method {config.method} requires existing data, but none was provided.")

        self._inject_dependency_timeframes(config, dataset_repository)

        method = InfillMethod.get(config.method)
        result = method.run(tf, config)
        self._add_flag(tf, result, tf.metadata["column_name"], config.method)
        return result

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
        return update_infill_core_flags(tf, self.get_core_flag_column(), self.get_flag_column())
