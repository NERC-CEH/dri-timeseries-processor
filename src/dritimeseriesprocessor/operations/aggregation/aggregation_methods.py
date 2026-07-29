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

        missing_criteria = AggregationMethod.missing_criteria(config)
        n = AggregationMethod.point_estimate_index(config)
        time_window = AggregationMethod.time_window(config)

        tf_agg = tf.aggregate(
            aggregation_period=config.params["aggregation_period"],
            aggregation_function=agg_func,
            aggregation_time_anchor=config.params["aggregation_time_anchor"],
            columns=col_name,
            missing_criteria=missing_criteria,  # type: ignore[assignment]
            n=n,
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
        alignment = config.params["alignment"]

        # Define number of datapoints in window from window_size and periodicity
        window_count = tf.periodicity.count(configure_period_object(window_size))

        missing_criteria = AggregationMethod.missing_criteria(config)
        time_window = AggregationMethod.time_window(config)

        # Calculate rolling mean across dataset
        tf_agg = tf.rolling_aggregate(
            window_size=window_size,
            aggregation_function=agg_func,
            columns=col_name,
            missing_criteria=missing_criteria,  # type: ignore[assignment]
            alignment=alignment,
            time_window=time_window,
        )

        # Default alignment = "center"
        rows_masked_at_start = window_count // 2
        rows_masked_at_end = window_count // 2

        if alignment == "trailing":
            rows_masked_at_start = window_count - 1
            rows_masked_at_end = 0
        elif alignment == "leading":
            rows_masked_at_start = 0
            rows_masked_at_end = window_count - 1

        row_index = pl.int_range(pl.len())
        truncated_window = (row_index >= rows_masked_at_start) & (row_index < pl.len() - rows_masked_at_end)

        tf_agg = tf_agg.with_df(
            tf_agg.df.with_columns(
                pl.when(truncated_window & pl.col(f"valid_{col_name}") & pl.col(agg_col_name).is_not_null())
                .then(pl.col(agg_col_name))
                .otherwise(None)
                .alias(col_name)
            )
        )

        return tf_agg

    @staticmethod
    def point_estimate_index(config: DataProcessingMethodConfig) -> int | None:
        point_estimate_index = None
        if config.params.get("n", None) is not None:
            point_estimate_index = config.params["n"] + 1  # index is 1-based
        return point_estimate_index

    @staticmethod
    def missing_criteria(config: DataProcessingMethodConfig) -> tuple[str, int] | None:
        missing_criteria = None
        if config.params.get("threshold", None) is not None:
            missing_criteria = ("available", config.params["threshold"])  # type: ignore[assignment]
        return missing_criteria

    @staticmethod
    def time_window(config: DataProcessingMethodConfig) -> tuple | None:
        start_time_str = config.params.get("start_time")
        end_time_str = config.params.get("end_time")
        if isinstance(start_time_str, str) and isinstance(end_time_str, str):
            start_time = datetime.strptime(start_time_str, "%H:%M:%S").time()
            end_time = datetime.strptime(end_time_str, "%H:%M:%S").time()
            return start_time, end_time
        return None


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
class PointEstimate(AggregationMethod):
    """
    Uses the nth (1-based) value in each aggregation period as the aggregation value.
    """

    name = "point_estimate"

    def run(self, tf: ts.TimeFrame, config: DataProcessingMethodConfig) -> ts.TimeFrame:
        return self._ts_aggregate(tf, config, "nth")


@AggregationMethod.register
class RollingMeanForCounts(AggregationMethod):
    """
    Calculates a mean for each data point from a window of surrounding datapoints on either side.
    Date points at the edges of a dataset, up to an index that is half the size of the window, are not assigned a mean.
    If there are too few datapoints available (eg. not null) within the window, the mean is assigned a null value.

    The window size and minimum threshold of datapoints required in the window are specified in the config parameters.
    """

    name = "rolling_mean_for_counts"

    def run(self, tf: ts.TimeFrame, config: DataProcessingMethodConfig) -> ts.TimeFrame:
        return self._ts_rolling_aggregate(tf, config, "mean")
