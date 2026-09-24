from abc import ABC

import time_stream as ts

from dritimeseriesprocessor.models.domain_models.processing_config import DataProcessingMethodConfig
from dritimeseriesprocessor.operations.operation_method import TransformMethod, observation_interval
from dritimeseriesprocessor.utils.enums import ConfigurationType


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
        return tf.infill(
            "alt_data",
            tf.metadata["column_name"],
            alt_df=config.params["alt_df"],
            alt_data_column=config.params["alt_data_column"],
            observation_interval=observation_interval(config),
            max_gap_size=config.params.get("max_gap_size"),
            correction_factor=config.params.get("correction_factor", 1),
        )


@InfillMethod.register
class AltDataDynamic(InfillMethod):
    name = "alt_data_dynamic"

    def run(self, tf: ts.TimeFrame, config: DataProcessingMethodConfig) -> ts.TimeFrame:
        return tf.infill(
            "alt_data_dynamic",
            tf.metadata["column_name"],
            alt_df=config.params["alt_df"],
            alt_data_column=config.params["alt_data_column"],
            observation_interval=observation_interval(config),
            max_gap_size=config.params.get("max_gap_size"),
            min_threshold=config.params.get("min_threshold", 0),
            max_threshold=config.params.get("max_threshold"),
            window_size=config.params["window"],
        )
