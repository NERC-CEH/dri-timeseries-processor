import time_stream as ts

from new_processor.utils.polars_utils import merge_multiple


def merge_multiple_timeframes(inputs: list[ts.TimeFrame]) -> ts.TimeFrame:
    time_name = inputs[0].time_name
    resolution = inputs[0].resolution
    periodicity = inputs[0].periodicity
    merged_df = merge_multiple([tf.df for tf in inputs], time_name)
    return ts.TimeFrame(merged_df, time_name, resolution=resolution, periodicity=periodicity)
