import polars as pl

from dritimeseriesprocessor.utils.time_stream_utils import merge_multiple_timeframes
from utils.data_creation import dataframe_to_timeframe


class TestMergeMultipleTimeframes:
    def test_merge_multiple_timeframes(self) -> None:
        """Test that multiple TimeFrames are merged correctly"""
        tf1 = dataframe_to_timeframe(pl.DataFrame({"a": [1, 2, 3]}))
        tf2 = dataframe_to_timeframe(pl.DataFrame({"b": [10, 20, 30]}))

        result = merge_multiple_timeframes([tf1, tf2])

        expected = dataframe_to_timeframe(pl.DataFrame({"a": [1, 2, 3], "b": [10, 20, 30]}))
        assert result == expected

    def test_merge_multiple_timeframes_diff_times(self) -> None:
        """Test that multiple TimeFrames with different times are merged correctly"""
        tf1 = dataframe_to_timeframe(pl.DataFrame({"a": [1, 2, 3]}))
        tf2 = dataframe_to_timeframe(pl.DataFrame({"b": [10, 20, 30]}), time_shift=1)
        tf3 = dataframe_to_timeframe(pl.DataFrame({"c": [100, 200, 300]}), time_shift=4)

        result = merge_multiple_timeframes([tf1, tf2, tf3])

        expected = dataframe_to_timeframe(
            pl.DataFrame(
                {
                    "a": [1, 2, 3, None, None, None, None],
                    "b": [None, 10, 20, 30, None, None, None],
                    "c": [None, None, None, None, 100, 200, 300],
                }
            ),
        )
        assert result == expected

    def test_single_input(self) -> None:
        """Test that a single input tf passes through unchanged"""
        tf1 = dataframe_to_timeframe(pl.DataFrame({"a": [1, 2, 3]}))
        result = merge_multiple_timeframes([tf1])
        assert result == tf1
