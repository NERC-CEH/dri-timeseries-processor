from abc import ABC, abstractmethod
from datetime import datetime
from typing import ClassVar, cast

import time_stream as ts
from time_stream.operation import Operation

from dritimeseriesprocessor.models.domain_models.processing_config import DataProcessingMethodConfig
from dritimeseriesprocessor.utils.enums import OperationType


class InfillMethod(Operation, ABC):
    operation_type: ClassVar[OperationType] = OperationType.INFILLING

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
            observation_interval=cast(tuple[datetime, datetime | None] | None, (config.start_date, config.end_date)),
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
            observation_interval=cast(tuple[datetime, datetime | None] | None, (config.start_date, config.end_date)),
            max_gap_size=config.params.get("max_gap_size"),
            correction_factor=config.params.get("correction_factor", 1),
        )
