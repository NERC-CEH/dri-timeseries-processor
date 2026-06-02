from abc import ABC, abstractmethod
from datetime import datetime

import time_stream as ts
from time_stream.operation import Operation

from dritimeseriesprocessor.models.domain_models.processing_config import DataProcessingMethodConfig
from dritimeseriesprocessor.utils.enums import OperationType


def _observation_interval(config: DataProcessingMethodConfig) -> tuple[datetime, datetime | None] | None:
    if config.start_date is None:
        return None
    return config.start_date, config.end_date


class InfillMethod(Operation, ABC):
    operation_type = OperationType.INFILLING

    @abstractmethod
    def run(self, *args, **kwargs) -> ts.TimeFrame:
        pass


@InfillMethod.register
class Linear(InfillMethod):
    name = "linear_linear"
    flag_value = 1

    def run(self, tf: ts.TimeFrame, config: DataProcessingMethodConfig) -> ts.TimeFrame:
        return tf.infill(
            "linear",
            tf.metadata["column_name"],
            observation_interval=_observation_interval(config),
            max_gap_size=config.params.get("max_gap_size"),
        )


@InfillMethod.register
class AltData(InfillMethod):
    name = "alt_data"
    flag_value = 2

    def run(self, tf: ts.TimeFrame, config: DataProcessingMethodConfig) -> ts.TimeFrame:
        return tf.infill(
            "alt_data",
            tf.metadata["column_name"],
            alt_df=config.params["alt_df"],
            alt_data_column=config.params["alt_data_column"],
            observation_interval=_observation_interval(config),
            max_gap_size=config.params.get("max_gap_size"),
            correction_factor=config.params.get("correction_factor", 1),
        )


@InfillMethod.register
class AltDataDynamic(InfillMethod):
    name = "alt_data_dynamic"
    flag_value = 4

    def run(self, tf: ts.TimeFrame, config: DataProcessingMethodConfig) -> ts.TimeFrame:
        return tf.infill(
            "alt_data_dynamic",
            tf.metadata["column_name"],
            alt_df=config.params["alt_df"],
            alt_data_column=config.params["alt_data_column"],
            observation_interval=_observation_interval(config),
            max_gap_size=config.params.get("max_gap_size"),
            min_threshold=config.params.get("min_threshold", 0),
            max_threshold=config.params.get("max_threshold"),
            window_size=config.params.get("window_size", 7),
        )
