from abc import ABC, abstractmethod
from datetime import datetime

import polars as pl
import time_stream as ts
from time_stream.operation import Operation
from time_stream.utils import configure_period_object

from dritimeseriesprocessor.models.domain_models.processing_config import DataProcessingMethodConfig
from dritimeseriesprocessor.utils.enums import ConfigurationType


class AggregationMethod(Operation, ABC):
    operation_type = ConfigurationType.AGGREGATION

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

        missing_criteria = None
        if config.params.get("threshold", None) is not None:
            missing_criteria = ("available", config.params["threshold"])  # type: ignore[assignment]

        time_window = None
        start_time_str = config.params.get("start_time")
        end_time_str = config.params.get("end_time")
        if isinstance(start_time_str, str) and isinstance(end_time_str, str):
            start_time = datetime.strptime(start_time_str, "%H:%M:%S").time()
            end_time = datetime.strptime(end_time_str, "%H:%M:%S").time()
            time_window = (start_time, end_time)

        tf_agg = tf.aggregate(
            aggregation_period=config.params["aggregation_period"],
            aggregation_function=agg_func,
            columns=col_name,
            missing_criteria=missing_criteria,  # type: ignore[assignment]
            time_window=time_window,
        )
        tf_agg = tf_agg.with_df(tf_agg.df.rename({agg_col_name: col_name}))

        return tf_agg

    @staticmethod
    def _ts_rolling_aggregate(tf: ts.TimeFrame, config: DataProcessingMethodConfig, agg_func: str) -> ts.TimeFrame:
        """Run a rolling aggregation using in-built methods in the Time-Stream package.

        Args:
            tf: TimeFrame to aggregate.
            config: Configuration options for the aggregation method.
            agg_func: The Time-Stream aggregation function to run.

        Returns:
            Aggregated TimeFrame.
        """
        col_name = tf.metadata["column_name"]
        agg_col_name = f"{agg_func}_{col_name}"
        window_size = config.params["window_size"]

        missing_criteria = None
        if config.params.get("threshold", None) is not None:
            missing_criteria = ("available", config.params["threshold"])  # type: ignore[assignment]

        time_window = None
        start_time_str = config.params.get("start_time")
        end_time_str = config.params.get("end_time")
        if isinstance(start_time_str, str) and isinstance(end_time_str, str):
            start_time = datetime.strptime(start_time_str, "%H:%M:%S").time()
            end_time = datetime.strptime(end_time_str, "%H:%M:%S").time()
            time_window = (start_time, end_time)

        # Define number of datapoints in window from window_size and periodicity
        window_count = tf.periodicity.count(configure_period_object(window_size))

        # Count total rows per window (nulls included) via an auxiliary column
        auxiliary_tf = ts.TimeFrame(
            df=tf.df.with_columns(pl.lit(1).cast(pl.UInt32).alias("__aux__")),
            time_name=tf.time_name,
            resolution=tf.resolution,
            periodicity=tf.periodicity,
        )

        # Determine number of datapoints per window across dataset
        total_in_window = auxiliary_tf.rolling_aggregate(
            window_size,
            "sum",
            columns=["__aux__"],
            alignment=config.params["alignment"],
        ).df.select([tf.time_name, pl.col("sum___aux__").alias("__total__")])

        # Calculate rolling mean across dataset
        tf_agg = tf.rolling_aggregate(
            window_size=window_size,
            aggregation_function=agg_func,
            columns=col_name,
            missing_criteria=missing_criteria,  # type: ignore[assignment]
            alignment=config.params["alignment"],
            time_window=time_window,
        )

        # Remove rolling aggregation values near edges where there is not enough data available.
        # This is because a timestamp may initially appear at the end of a dataset, but as data gets added,
        # it will no longer be at the end of the dataset, and the rolling aggregation value will change.
        # Applying a rolling aggregation only when there is enough data ensures consistency.
        tf_agg = tf_agg.with_df(
            tf_agg.df.join(total_in_window, on=tf.time_name)
            .with_columns(
                pl.when(
                    (pl.col("__total__") == window_count) & (pl.col(f"count_{col_name}") >= config.params["threshold"])
                )
                .then(pl.col(f"{agg_func}_{col_name}"))
                .otherwise(None)
                .alias(f"{agg_func}_{col_name}")
            )
            .drop("__total__")
        )

        # Filter for valid columns only
        tf_agg = tf_agg.with_df(
            tf_agg.df.with_columns(
                pl.when(pl.col(f"valid_{col_name}")).then(pl.col(agg_col_name)).otherwise(None).alias(col_name)
            )
        )

        return tf_agg


@AggregationMethod.register
class MeanRad(AggregationMethod):
    """A specific aggregation method for calculating mean of radiation data.

    Radiation is measured as:               W m-2 = Js-1 m-2
    Mean radiation should be output as:     MJ[aggregation period]-1 m-2

    e.g. MJ day-1 m-2 = (seconds in a day/10^6) * Js-1 m-2

    References:
        https://www.fao.org/4/x0490e/x0490e0i.htm
    """

    name = "mean_rad"

    def run(self, tf: ts.TimeFrame, config: DataProcessingMethodConfig) -> ts.TimeFrame:
        col_name = tf.metadata["column_name"]
        seconds_in_agg_period = config.params["aggregation_period"].timedelta.total_seconds()

        tf_agg = self._ts_aggregate(tf, config, "mean")
        tf_agg = tf_agg.with_df(
            tf_agg.df.with_columns((pl.col(col_name) * seconds_in_agg_period / 1e6).alias(col_name))
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
class MeanSum(AggregationMethod):
    name = "mean_sum"

    def run(self, tf: ts.TimeFrame, config: DataProcessingMethodConfig) -> ts.TimeFrame:
        return self._ts_aggregate(tf, config, "mean_sum")


@AggregationMethod.register
class AngularMean(AggregationMethod):
    name = "angular_mean"

    def run(self, tf: ts.TimeFrame, config: DataProcessingMethodConfig) -> ts.TimeFrame:
        return self._ts_aggregate(tf, config, "angular_mean")


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
class StandardDeviation(AggregationMethod):
    name = "stdev"

    def run(self, tf: ts.TimeFrame, config: DataProcessingMethodConfig) -> ts.TimeFrame:
        return self._ts_aggregate(tf, config, "stdev")


@AggregationMethod.register
class RollingMeanForCounts(AggregationMethod):
    name = "rolling_mean_for_counts"

    def run(self, tf: ts.TimeFrame, config: DataProcessingMethodConfig) -> ts.TimeFrame:
        config.params.setdefault("window_size", "PT25H")
        config.params.setdefault("alignment", "center")
        config.params.setdefault("threshold", 21)
        return self._ts_rolling_aggregate(tf, config, "mean")
