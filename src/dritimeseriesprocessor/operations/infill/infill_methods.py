from abc import ABC

import polars as pl
import time_stream as ts
from time_stream.utils import get_date_filter

from dritimeseriesprocessor.models.domain_models.processing_config import DataProcessingMethodConfig
from dritimeseriesprocessor.operations.operation_method import TransformMethod, observation_interval
from dritimeseriesprocessor.utils.enums import ConfigurationType
from dritimeseriesprocessor.utils.polars_utils import missing_expr


class InfillMethod(TransformMethod[ts.TimeFrame], ABC):
    operation_type = ConfigurationType.INFILLING


@InfillMethod.register
class Linear(InfillMethod):
    name = "linear_interp"

    def run(self, tf: ts.TimeFrame, config: DataProcessingMethodConfig) -> ts.TimeFrame:
        return tf.infill(
            "linear",
            tf.metadata["column_name"],
            observation_interval=observation_interval(config),
            max_gap_size=config.params.get("max_gap_size"),
        )


@InfillMethod.register
class AltData(InfillMethod):
    name = "alt_data"

    def run(self, tf: ts.TimeFrame, config: DataProcessingMethodConfig) -> ts.TimeFrame:
        alt_tf = config.params["alt_data_source"]
        return tf.infill(
            "alt_data",
            tf.metadata["column_name"],
            alt_df=alt_tf.df,
            alt_data_column=alt_tf.metadata["column_name"],
            observation_interval=observation_interval(config),
            max_gap_size=config.params.get("max_gap_size"),
            correction_factor=config.params.get("correction_factor", 1),
        )


@InfillMethod.register
class AltDataDynamic(InfillMethod):
    name = "alt_data_dynamic"

    def run(self, tf: ts.TimeFrame, config: DataProcessingMethodConfig) -> ts.TimeFrame:
        alt_tf = config.params["alt_data_source"]
        return tf.infill(
            "alt_data_dynamic",
            tf.metadata["column_name"],
            alt_df=alt_tf.df,
            alt_data_column=alt_tf.metadata["column_name"],
            observation_interval=observation_interval(config),
            max_gap_size=config.params.get("max_gap_size"),
            min_threshold=config.params.get("min_threshold", 0),
            max_threshold=config.params.get("max_threshold"),
            window_size=config.params["window"],
        )


@InfillMethod.register
class ZeroFill(InfillMethod):
    """Fill every missing value with 0, e.g. snow depth, which reads slightly negative when there is no snow."""

    name = "zero_fill"

    def run(self, tf: ts.TimeFrame, config: DataProcessingMethodConfig) -> ts.TimeFrame:
        col_name = tf.metadata["column_name"]
        dtype = tf.df.schema[col_name]
        in_dates = get_date_filter(tf.time_name, (config.start_date, config.end_date), tf.df.schema[tf.time_name])
        fill = missing_expr(col_name, dtype) & in_dates
        expr = pl.when(fill).then(pl.lit(0).cast(dtype)).otherwise(pl.col(col_name)).alias(col_name)
        return tf.with_df(tf.df.with_columns(expr))
