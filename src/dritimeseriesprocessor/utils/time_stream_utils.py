import time_stream as ts
from time_stream.types import TimeAnchor

from dritimeseriesprocessor.utils.polars_utils import merge_multiple


def merge_multiple_timeframes(inputs: list[ts.TimeFrame]) -> ts.TimeFrame:
    time_name = inputs[0].time_name
    resolution = inputs[0].resolution
    periodicity = inputs[0].periodicity
    time_anchor = inputs[0].time_anchor

    # Double check all the inputs conform to the same time properties
    if not all([tf.time_name == time_name for tf in inputs]):
        raise ValueError("Not all inputs to `merge_multiple_timeframes` have the same time name")

    if not all([tf.resolution == resolution for tf in inputs]):
        raise ValueError("Not all inputs to `merge_multiple_timeframes` have the same resolution")

    if not all([tf.periodicity == periodicity for tf in inputs]):
        raise ValueError("Not all inputs to `merge_multiple_timeframes` have the same periodicity")

    if not all([tf.time_anchor == time_anchor for tf in inputs]):
        raise ValueError("Not all inputs to `merge_multiple_timeframes` have the same time anchor")

    merged_df = merge_multiple([tf.df for tf in inputs], time_name)
    return ts.TimeFrame(
        merged_df.sort(time_name), time_name, resolution=resolution, periodicity=periodicity, time_anchor=time_anchor
    )


def map_time_anchor(time_anchor: str) -> TimeAnchor:
    """Map metadata time-anchor semantics to the values used in time-stream

    Args:
        time_anchor: Time anchor from the metadata service

    Returns:
        Time anchor string to use in time-stream TimeFrames
    """
    if time_anchor == "proc":
        return "start"
    elif time_anchor == "prec":
        return "end"
    elif time_anchor == "inst":
        return "point"
    else:
        raise ValueError(f"Unhandled time anchor value: {time_anchor}")
