from abc import ABC, abstractmethod

import polars as pl
import time_stream as ts
from time_stream.operation import Operation

from dritimeseriesprocessor.models.domain_models.processing_config import ProcessingMethodConfig
from dritimeseriesprocessor.utils.enums import OperationType


class AggregationMethod(Operation, ABC):
    operation_type: OperationType.AGGREGATION

    @abstractmethod
    def run(self, *args, **kwargs) -> ts.TimeFrame:
        pass

    @staticmethod
    def _ts_aggregate(tf: ts.TimeFrame, config: ProcessingMethodConfig, agg_func: str) -> ts.TimeFrame:
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
class WD(AggregationMethod):
    # See: https://en.wikipedia.org/wiki/Yamartino_method for formula
    name = "agg_daily_wd"

    def run(self, wd: ts.TimeFrame, config: ProcessingMethodConfig) -> ts.TimeFrame:
        # Config specifies aggregate sum of each day

        col_name = wd.metadata["column_name"]

        # Calculate sin and cos of data cols
        wd_sin_cos_tf = wd.with_df(
            wd.df.with_columns(
                [
                    pl.col(col_name).radians().sin().alias("sin_value"),
                    pl.col(col_name).radians().cos().alias("cos_value"),
                ]
            )
        )

        # Take daily aggregate
        daily_wd_sin_cos_tf = wd_sin_cos_tf.aggregate("P1D", "sum")

        # Calculate arctan of daily aggregate of sin/cos
        daily_wd_tf = daily_wd_sin_cos_tf.with_df(
            daily_wd_sin_cos_tf.df.with_columns(
                pl.arctan2(pl.col("sum_sin_value"), pl.col("sum_cos_value")).degrees().alias("daily_wd")
            )
        ).select("daily_wd")

        # Result should have single data column with name 'WD', same as original wd dataset.
        daily_wd_tf = daily_wd_tf.with_df(daily_wd_tf.df.rename({"daily_wd": col_name}))

        return daily_wd_tf


@AggregationMethod.register
class Sum(AggregationMethod):
    name = "sum"

    def run(self, tf: ts.TimeFrame, config: ProcessingMethodConfig) -> ts.TimeFrame:
        return self._ts_aggregate(tf, config, "sum")


@AggregationMethod.register
class Mean(AggregationMethod):
    name = "mean"

    def run(self, tf: ts.TimeFrame, config: ProcessingMethodConfig) -> ts.TimeFrame:
        return self._ts_aggregate(tf, config, "mean")


@AggregationMethod.register
class Max(AggregationMethod):
    name = "max"

    def run(self, tf: ts.TimeFrame, config: ProcessingMethodConfig) -> ts.TimeFrame:
        return self._ts_aggregate(tf, config, "max")


@AggregationMethod.register
class Min(AggregationMethod):
    name = "min"

    def run(self, tf: ts.TimeFrame, config: ProcessingMethodConfig) -> ts.TimeFrame:
        return self._ts_aggregate(tf, config, "min")
