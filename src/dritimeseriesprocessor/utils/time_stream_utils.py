import time_stream as ts

from dritimeseriesprocessor.utils.polars_utils import merge_multiple


def merge_multiple_timeframes(inputs: list[ts.TimeFrame]) -> ts.TimeFrame:
    time_name = inputs[0].time_name
    resolution = inputs[0].resolution
    periodicity = inputs[0].periodicity

    # Double check all the inputs conform to the same time properties
    if not all([tf.time_name == time_name for tf in inputs]):
        raise ValueError("Not all inputs to `merge_multiple_timeframes` have the same time name")

    if not all([tf.resolution == resolution for tf in inputs]):
        raise ValueError("Not all inputs to `merge_multiple_timeframes` have the same resolution")

    if not all([tf.periodicity == periodicity for tf in inputs]):
        raise ValueError("Not all inputs to `merge_multiple_timeframes` have the same periodicity")

    merged_df = merge_multiple([tf.df for tf in inputs], time_name)
    return ts.TimeFrame(merged_df, time_name, resolution=resolution, periodicity=periodicity)
