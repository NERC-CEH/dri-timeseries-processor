from abc import ABC, abstractmethod

import polars as pl
import time_stream as ts
from time_stream.enums import MissingCriteria
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
        validity_col_name = f"valid_{col_name}"

        missing_criteria = None
        if config.argument.get("threshold", None) is not None:
            missing_criteria = (MissingCriteria.AVAILABLE, config.argument["threshold"])

        tf_agg = tf.aggregate(
            aggregation_period=config.params["aggregation_period"],
            aggregation_function=agg_func,
            columns=col_name,
            missing_criteria=missing_criteria,
        ).select([agg_col_name, validity_col_name])

        # Replace any rows where the validity check has failed with None. These can then be picked up
        # during the core flag initialisation as invalid.
        tf_agg = tf_agg.with_df(
            tf_agg.df.with_columns(
                pl.when(validity_col_name)
                .then(agg_col_name)
                .otherwise(None)
                .cast(tf_agg.df[agg_col_name].dtype)
                .alias(agg_col_name)
            )
        ).select(agg_col_name)

        tf_agg = tf_agg.with_df(tf_agg.df.rename({agg_col_name: col_name}))

        # Apply any rounding if required
        if config.argument.get("round", None) is not None:
            tf_agg = tf_agg.with_df(
                tf_agg.df.with_columns(pl.col(col_name).round(config.argument["round"]).alias(col_name))
            )

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
class WD(AggregationMethod):
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
