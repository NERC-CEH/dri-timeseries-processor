from abc import ABC, abstractmethod
from datetime import datetime
from typing import ClassVar

import polars as pl
import time_stream as ts
from time_stream.enums import MissingCriteria
from time_stream.operation import Operation

from dritimeseriesprocessor.models.domain_models.processing_config import DataProcessingMethodConfig
from dritimeseriesprocessor.utils.enums import OperationType


class AggregationMethod(Operation, ABC):
    operation_type: ClassVar[OperationType] = OperationType.AGGREGATION

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

        missing_criteria: tuple[str, float | int] | None = None
        if config.params.get("threshold", None) is not None:
            missing_criteria = (MissingCriteria.AVAILABLE.value, config.params["threshold"])

        time_window = None
        start_time_str = config.params.get("start_time")
        end_time_str = config.params.get("end_time")
        if start_time_str and end_time_str:
            start_time = datetime.strptime(start_time_str, "%H:%M:%S").time()
            end_time = datetime.strptime(end_time_str, "%H:%M:%S").time()
            time_window = (start_time, end_time)

        tf_agg = tf.aggregate(
            aggregation_period=config.params["aggregation_period"],
            aggregation_function=agg_func,
            columns=col_name,
            missing_criteria=missing_criteria,
            time_window=time_window,
        )
        tf_agg = tf_agg.with_df(tf_agg.df.rename({agg_col_name: col_name}))

        return tf_agg


@AggregationMethod.register
class MeanRad(AggregationMethod):
    # Radiation is measured as: W m-2 = Js-1 m-2
    # Mean radiation should be output as MJ[aggregation period]-1 m-2
    # e.g. MJday-1 m-2 = (seconds in a day/10^6)*Js-1 m-2
    # See https://www.fao.org/4/x0490e/x0490e0i.htm for conversion

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
