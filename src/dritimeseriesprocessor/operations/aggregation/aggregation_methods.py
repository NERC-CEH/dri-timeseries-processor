from abc import ABC, abstractmethod

import polars as pl
import time_stream as ts
from time_stream.operation import Operation

from dritimeseriesprocessor.models.domain_models.processing_config import DataProcessingMethodConfig
from dritimeseriesprocessor.utils.enums import OperationType


class AggregationMethod(Operation, ABC):
    operation_type: OperationType.AGGREGATION

    @abstractmethod
    def run(self, *args, **kwargs) -> ts.TimeFrame:
        pass

    @staticmethod
    def _ts_aggregate(tf: ts.TimeFrame, config: DataProcessingMethodConfig, agg_func: str) -> ts.TimeFrame:
        """Run an aggregation using in-built methods in the Time-Stream package.

        Args:
            tf: TimeFrame to aggregate.
            config: Configuration options for the aggregation method.
            agg_func: The Time-Stream aggregation function to run.

        Returns:
            Aggregated TimeFrame.
        """
        col_name = tf.metadata["column_name"]
        agg_col_name = f"{agg_func}_{col_name}"

        tf_agg = tf.aggregate(
            aggregation_period=config.params["aggregation_period"],
            aggregation_function=agg_func,
            columns=col_name,
        ).select(agg_col_name)

        tf_agg = tf_agg.with_df(tf_agg.df.rename({agg_col_name: col_name}))

        # Apply any rounding if required
        if config.argument.get("round", None) is not None:
            tf_agg = tf_agg.with_df(
                tf_agg.df.with_columns(pl.col(col_name).round(config.argument["round"]).alias(col_name))
            )

        return tf_agg


@AggregationMethod.register
class Sum(AggregationMethod):
    name = "sum"

    def run(self, tf: ts.TimeFrame, config: DataProcessingMethodConfig) -> ts.TimeFrame:
        return self._ts_aggregate(tf, config, "sum")


@AggregationMethod.register
class Mean(AggregationMethod):
    name = "mean"

    def run(self, tf: ts.TimeFrame, config: DataProcessingMethodConfig) -> ts.TimeFrame:
        return self._ts_aggregate(tf, config, "mean")


@AggregationMethod.register
class Max(AggregationMethod):
    name = "max"

    def run(self, tf: ts.TimeFrame, config: DataProcessingMethodConfig) -> ts.TimeFrame:
        return self._ts_aggregate(tf, config, "max")


@AggregationMethod.register
class Min(AggregationMethod):
    name = "min"

    def run(self, tf: ts.TimeFrame, config: DataProcessingMethodConfig) -> ts.TimeFrame:
        return self._ts_aggregate(tf, config, "min")


@AggregationMethod.register
class PE(AggregationMethod):

    name = "mean_pe"

    def run(self, tf: ts.TimeFrame, config: DataProcessingMethodConfig) -> ts.TimeFrame:
        col_name = tf.metadata["column_name"]
        agg_period = config.params["aggregation_period"]

        tf_agg = tf.with_df(tf.df.filter(pl.col(col_name) > 0)).aggregate(agg_period.iso_duration, "mean_sum")
        tf_agg = tf_agg.select(f"mean_sum_{col_name}")

        # Adds flag column: states whether or not the threshold number of data points is met.
        tf_agg.register_flag_system("qc_flags", {"HEIGHT": 1})
        tf_agg.init_flag_column(f"mean_sum_{col_name}", "qc_flags")
        if tf.df.height >= config.params["threshold"]: #44
            tf_agg.add_flag(f"mean_sum__flag__qc_flags", 1)

        # Resulting data column should have same name as original dataset with flag column
        tf_agg = tf_agg.with_df(tf_agg.df.rename({f"mean_sum_{col_name}": col_name}))

        return tf_agg
