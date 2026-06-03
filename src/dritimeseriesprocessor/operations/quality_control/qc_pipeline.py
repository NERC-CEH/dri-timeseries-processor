import logging

import polars as pl
import time_stream as ts

from dritimeseriesprocessor.models.domain_models.processing_config import (
    DataProcessingMethodConfig,
)
from dritimeseriesprocessor.operations.flags.flag_methods import update_quality_control_core_flags
from dritimeseriesprocessor.operations.flags.flag_names import QC_FLAG_SYS_NAME, qc_flag_column_name
from dritimeseriesprocessor.operations.operation_pipeline import OperationPipeline
from dritimeseriesprocessor.operations.quality_control.qc_methods import QcMethod
from dritimeseriesprocessor.utils.enums import ConfigurationType

logger = logging.getLogger(__name__)


class QCPipeline(OperationPipeline):
    """Pipeline for running Quality Control (QC) checks on a TimeSeriesContainer."""

    def __init__(self):
        super().__init__(ConfigurationType.QUALITY_CONTROL, QC_FLAG_SYS_NAME)

    def run(self, *args, **kwargs) -> ts.TimeFrame:
        """Override the parent run method, as we need to remove QC'ed data at the end of the pipeline after all
        QC tests have run.
        """
        tf = super().run(*args, **kwargs)
        return self._remove_data(tf)

    def apply(self, tf: ts.TimeFrame, config: DataProcessingMethodConfig, dataset_repository: dict) -> ts.TimeFrame:
        """Apply the given quality control method to the TimeFrame data.

        Args:
            tf: Time series frame to process.
            config: Configuration of the quality control method.
            dataset_repository: Repository for accessing additional datasets.

        Returns:
            Result of applying the QC method.
        """
        if "dep_ts" in config.params:
            tf_qc = dataset_repository[config.params["dep_ts"]].data
        else:
            tf_qc = tf.copy(share_df=False)

        method = QcMethod.get(config.method)
        result = method.run(tf_qc, config)

        result = tf.with_df(
            tf.df.with_columns(pl.Series(self.get_qc_result_column(tf.metadata["column_name"]), result))
        )
        self._add_flag(tf, result, tf.metadata["column_name"], config.method)
        result = result.with_df(result.df.drop(self.get_qc_result_column(tf.metadata["column_name"])))

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

    def _remove_data(self, tf: ts.TimeFrame) -> ts.TimeFrame:
        """Remove data that has failed the qc check

        Args:
            tf: TimeFrame to remove bad data from.

        Returns:
            TimeFrame with bad data removed.
        """
        df_qc = tf.df.with_columns(
            pl.when(pl.col(self.get_flag_column(tf.metadata["column_name"])) > 0)
            .then(None)
            .otherwise(pl.col(tf.metadata["column_name"]))
            .alias(tf.metadata["column_name"])
        )

        return tf.with_df(df_qc)
