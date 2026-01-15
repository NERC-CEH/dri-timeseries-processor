from abc import ABC, abstractmethod

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
        return tf_agg


@AggregationMethod.register
class Sum(AggregationMethod):
    name = "aggregate-sum"

    def run(self, tf: ts.TimeFrame, config: ProcessingMethodConfig) -> ts.TimeFrame:
        return self._ts_aggregate(tf, config, "sum")


@AggregationMethod.register
class Mean(AggregationMethod):
    name = "aggregate-mean"

    def run(self, tf: ts.TimeFrame, config: ProcessingMethodConfig) -> ts.TimeFrame:
        return self._ts_aggregate(tf, config, "mean")


@AggregationMethod.register
class Max(AggregationMethod):
    name = "aggregate-max"

    def run(self, tf: ts.TimeFrame, config: ProcessingMethodConfig) -> ts.TimeFrame:
        return self._ts_aggregate(tf, config, "max")


@AggregationMethod.register
class Min(AggregationMethod):
    name = "aggregate-min"

    def run(self, tf: ts.TimeFrame, config: ProcessingMethodConfig) -> ts.TimeFrame:
        return self._ts_aggregate(tf, config, "min")
