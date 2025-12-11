from abc import ABC, abstractmethod

import time_stream as ts
from time_stream.operation import Operation

from new_processor.models.domain_models.processing_config import ProcessingMethodConfig
from new_processor.utils.enums import OperationType


class InfillMethod(Operation, ABC):
    operation_type: OperationType.INFILLING

    @abstractmethod
    def run(self, *args, **kwargs) -> ts.TimeFrame:
        pass


@InfillMethod.register
class Linear(InfillMethod):
    name = "linear_linear"
    flag_value = 1

    def run(self, tf: ts.TimeFrame, config: ProcessingMethodConfig) -> ts.TimeFrame:
        return tf.infill(
            "linear",
            tf.metadata["column_name"],
            observation_interval=(config.start_date, config.end_date),
        )


@InfillMethod.register
class AltData(InfillMethod):
    name = "alt_data"
    flag_value = 2

    def run(self, tf: ts.TimeFrame, config: ProcessingMethodConfig) -> ts.TimeFrame:
        return tf.infill(
            "alt_data",
            tf.metadata["column_name"],
            alt_df=config.params["alt_df"],
            alt_data_column=config.params["alt_data_column"],
            observation_interval=(config.start_date, config.end_date),
        )
