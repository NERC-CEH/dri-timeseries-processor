import logging
from typing import Iterable

import polars as pl
import time_stream as ts

from dritimeseriesprocessor.models.domain_models.processing_config import (
    DataProcessingConfig,
    DataProcessingMethodConfig,
)
from dritimeseriesprocessor.models.domain_models.time_series_container import TimeSeriesContainer
from dritimeseriesprocessor.operations.flags.flag_methods import update_infill_core_flags
from dritimeseriesprocessor.operations.flags.flag_names import INFILL_FLAG_SYS_NAME, infill_flag_column_name
from dritimeseriesprocessor.operations.infill.infill_metadata_names import (
    INFILL_META_INTERNAL_COL,
    infill_meta_column_name,
)
from dritimeseriesprocessor.operations.infill.infill_methods import InfillMethod
from dritimeseriesprocessor.operations.operation_pipeline import OperationPipeline
from dritimeseriesprocessor.utils.enums import OperationType

logger = logging.getLogger(__name__)


class InfillPipeline(OperationPipeline):
    """Processor for running infilling on a TimeSeriesContainer."""

    def __init__(self):
        super().__init__(OperationType.INFILLING, INFILL_FLAG_SYS_NAME)

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
        result = self._attach_infill_meta(result, tf.metadata["column_name"])
        return result

    def get_configs(self, container: TimeSeriesContainer) -> set[DataProcessingConfig]:
        """Extract the infill method configurations.

        Args:
            container: Time series container to get the infill method configurations from.

        Returns:
            List of infill configurations to be applied.
        """
        return container.infill_configs

    def sort_configs(self, configs: Iterable[DataProcessingConfig]) -> list[DataProcessingConfig]:
        """Sort the infilling configs into the correct order based on their "priority"

        Args:
            configs: List of infill configurations to be sorted.

        Returns:
            Sorted list of infill configurations
        """
        return sorted(configs, key=lambda cfg: cfg.annotations.get("priority", 0))

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

    def _attach_infill_meta(self, result: ts.TimeFrame, col_name: str) -> ts.TimeFrame:
        """Consume the internal infill metadata column from time_stream and accumulate it
        into the persistent per-column metadata column.

        time_stream writes per-row infill metadata as JSON strings into a temporary
        column named ``__INFILL_META__``. This method renames it to the stable output
        column name and coalesces it with any values already written by earlier infill
        passes so that each row retains the metadata from whichever method filled it.

        Args:
            result: TimeFrame returned by the infill method.
            col_name: Name of the data column being infilled.

        Returns:
            TimeFrame with ``__INFILL_META__`` consumed and accumulated into
            ``{col_name}_INFILL_META``.
        """
        if INFILL_META_INTERNAL_COL not in result.df.columns:
            return result

        meta_col = infill_meta_column_name(col_name)
        new_meta = pl.col(INFILL_META_INTERNAL_COL)

        if meta_col in result.df.columns:
            merged = pl.coalesce(pl.col(meta_col), new_meta).alias(meta_col)
        else:
            merged = new_meta.alias(meta_col)

        return result.with_df(result.df.with_columns(merged).drop(INFILL_META_INTERNAL_COL))

    def core_flag_updater(self, tf: ts.TimeFrame) -> ts.TimeFrame:
        """Update core flags with the infill flag after all methods are applied.

        Args:
            tf: TimeFrame with flags to update.

        Returns:
            Timeframe with updated core flags
        """
        return update_infill_core_flags(tf)
