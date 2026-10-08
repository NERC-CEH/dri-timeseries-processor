import logging

import polars as pl
import time_stream as ts

from dritimeseriesprocessor.models.domain_models.processing_config import (
    DataProcessingConfig,
    DataProcessingMethodConfig,
)
from dritimeseriesprocessor.models.domain_models.time_series_container import TimeSeriesContainer
from dritimeseriesprocessor.operations.flags.flag_methods import update_quality_control_core_flags
from dritimeseriesprocessor.operations.flags.flag_names import core_flag_column_name, qc_flag_column_name
from dritimeseriesprocessor.operations.operation_pipeline import OperationPipeline
from dritimeseriesprocessor.operations.quality_control.qc_methods import QcMethod
from dritimeseriesprocessor.utils.enums import ConfigurationType
from dritimeseriesprocessor.utils.polars_utils import not_missing_expr

logger = logging.getLogger(__name__)


class QCPipeline(OperationPipeline):
    """Pipeline for running Quality Control (QC) checks on a TimeSeriesContainer."""

    def __init__(self, flag_systems: dict[str, dict[str, int]]):
        super().__init__(ConfigurationType.QUALITY_CONTROL, flag_systems)

    def run(
        self,
        container: TimeSeriesContainer,
        dataset_repository: dict[str, TimeSeriesContainer],
        config: DataProcessingConfig,
        *,
        remove_flagged: bool = True,
    ) -> ts.TimeFrame:
        """Run QC checks and, if this is the last QC block in the plan, remove data that failed."""
        # Checks that need to know which site they are running on (e.g. manual_removal) read these. Other checks
        # ignore them.
        for cfg in config.method_configs:
            cfg.params["network"] = container.network
            cfg.params["site_id"] = container.source_site_identifier

        tf = super().run(container, dataset_repository, config)
        if remove_flagged and container.has_flags():
            logger.info("Removing data that has failed QC checks")
            tf = self.remove_flagged_data(tf)  # type: ignore[arg-type]
        return tf

    def apply(
        self, tf: ts.TimeFrame | None, config: DataProcessingMethodConfig, dataset_repository: dict
    ) -> ts.TimeFrame:
        """Apply the given quality control method to the TimeFrame data.

        Args:
            tf: Time series frame to process.
            config: Configuration of the quality control method.
            dataset_repository: Repository for accessing additional datasets.

        Returns:
            Result of applying the QC method.
        """
        if tf is None:
            raise ValueError(f"QC method {config.method} requires existing data, but none was provided.")

        self._inject_dependency_timeframes(config, dataset_repository)

        method = QcMethod.get(config.method)
        qc_result = method.run(tf, config)
        qc_result_column = self.get_qc_result_column(tf.metadata["column_name"])

        result = tf.with_df(tf.df.with_columns(qc_result.alias(qc_result_column)))
        self._add_flag(tf, result, tf.metadata["column_name"], config.method)
        result = result.with_df(result.df.drop(qc_result_column))

        return result

    def get_flag_column(self, column: str) -> str:
        """Determine the QC flag column name for a given data column.

        Args:
            column: Name of the data column.

        Returns:
            Name of the corresponding QC flag column.
        """
        return qc_flag_column_name(column)

    def compute_flag_mask(self, tf: ts.TimeFrame, result: ts.TimeFrame, column_name: str) -> pl.Series:
        """Return an object that can be used to determine the mask for adding a flag to the flag column.

        For QC, the flag mask is just the result of the qc check - i.e. 1 = qc check failed, 0 = qc check passed

        Args:
            tf: Original TimeFrame being processed.
            result: Result from applying a method to tf.
            column_name: Name of the column being processed.

        Returns:
            Result of QC check
        """
        return result.df[self.get_qc_result_column(column_name)]

    def core_flag_updater(self, tf: ts.TimeFrame) -> ts.TimeFrame:
        """Update core flags with the QC flag after all methods are applied.

        Args:
            tf: TimeFrame with flags to update.

        Returns:
            Timeframe with updated core flags
        """
        return update_quality_control_core_flags(tf)

    @staticmethod
    def get_qc_result_column(column: str) -> str:
        """Get a temporary column name for the result of the qc check on a given data column.

        Args:
            column: Name of the data column.

        Returns:
            Name of the corresponding qc result column.
        """
        return f"__qc_result_{column}"

    @staticmethod
    def remove_flagged_data(tf: ts.TimeFrame) -> ts.TimeFrame:
        """Remove data that has failed any QC check, and add the "removed" core flag to the values that were removed.

        Only values that were present get the "removed" flag. A value that was already null had nothing to remove,
        even if a check flagged it (e.g. `samples` or `manual_removal`, which flag rows whatever their value).

        Args:
            tf: TimeFrame to remove bad data from.

        Returns:
            TimeFrame with flagged data removed.
        """
        col_name = tf.metadata["column_name"]
        flag_col = qc_flag_column_name(col_name)
        failed_qc = pl.col(flag_col) > 0

        # Take into account values that were already NULL
        removed = (
            tf.df.select(failed_qc & not_missing_expr(col_name, tf.df[col_name].dtype)).to_series().fill_null(False)
        )
        df_qc = tf.df.with_columns(pl.when(failed_qc).then(None).otherwise(pl.col(col_name)).alias(col_name))
        tf = tf.with_df(df_qc)

        # Set the removed flag - this is the only point we can tell whether the data was removed by us, or was null to
        # start with
        core_flag_col = core_flag_column_name(col_name)
        if core_flag_col in tf.flag_columns:
            tf.add_flag(core_flag_col, "removed", removed)
        return tf
