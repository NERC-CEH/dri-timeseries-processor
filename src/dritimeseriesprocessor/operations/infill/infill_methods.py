from abc import ABC, abstractmethod

import time_stream as ts
from time_stream.operation import Operation

from dritimeseriesprocessor.models.domain_models.processing_config import DataProcessingMethodConfig
from dritimeseriesprocessor.utils.enums import OperationType


class InfillMethod(Operation, ABC):
    operation_type: OperationType.INFILLING

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
            observation_interval=(config.start_date, config.end_date),
            max_gap_size=config.params.get("max_gap_size"),
        )


@InfillMethod.register
class AltData(InfillMethod):
    name = "alt_data"
    flag_value = 2

    # Threshold:
    # In a 7 day period either side of gap, use nearest 24hours on each side to calculate correction factor.
    # Otherwise, use at least 6 data points, and up to 24 data points, either side of gap.
    # If there are not a total of 12 data points, other alternative data or infilling method must be used.

    # What should the max gap size be?

    def run(self, tf: ts.TimeFrame, config: DataProcessingMethodConfig) -> ts.TimeFrame:
        # if "window" in config.params:
        # window = config.params["window"]

        # See utils for pad_time and gap_size methods for infill in timestream
        # df = pad_time(tf.df, tf.time_name, tf.periodicity)
        # df = gap_size_count(df, tf.metadata["column_name"])
        # for gap_size in df["gap_size"]:
        #    if gap_size!=0 and gap_size <= "PT3D":
        # get location of start and end of gap
        # get data for 7 days either side of gap from df and config.params["alt_df"]
        # to get this data, use config.params["window"], which can be set to 7 days in the metadata.
        # check size of gap is not above max gap size, use config/params["max_gap"] = int
        # check if consecutive 24 hours of data either side of gap for alt_df
        # if not, check if at least 6 data points (and up to 24) either side of gap for alt df
        # if not, use alt_df next in priority or alternative infilling method
        # if criteria met, sum data for df and alt_df and divide one by other to get correction_factor
        # save correction factor in new column in df: null if not in gap,
        # or save same correction factor value for each entry in gap.
        # return df as tf, or simply return correction factor as polars expr/df col.

        # update altdata in timestream to use correction factor as a float OR as a df column.
        # else:
        correction_factor = config.params.get("correction_factor")
        return tf.infill(
            "alt_data",
            tf.metadata["column_name"],
            alt_df=config.params["alt_df"],
            alt_data_column=config.params["alt_data_column"],
            observation_interval=(config.start_date, config.end_date),
            max_gap_size=config.params.get("max_gap_size"),
            correction_factor=correction_factor,
        )
