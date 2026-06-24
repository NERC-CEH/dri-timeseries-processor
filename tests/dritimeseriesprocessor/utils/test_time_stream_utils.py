from datetime import datetime, timedelta

import polars as pl
import pytest
import time_stream as ts

from dritimeseriesprocessor.utils.time_stream_utils import map_time_anchor, merge_multiple_timeframes
from utils.data_creation import dataframe_to_timeframe


class TestMapTimeAnchor:
    @pytest.mark.parametrize(
        "time_anchor, expected",
        [
            ("proc", "start"),
            ("prec", "end"),
            ("inst", "point"),
        ],
    )
    def test_maps_metadata_anchor_to_time_stream_anchor(self, time_anchor: str, expected: str) -> None:
        """Tests that each metadata time anchor maps to the matching time-stream anchor"""
        assert map_time_anchor(time_anchor) == expected

    def test_unhandled_anchor_raises(self) -> None:
        """Tests that an unrecognised time anchor raises a ValueError"""
        with pytest.raises(ValueError):
            map_time_anchor("unknown")


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

    def test_merge_diff_time_names_raises(self) -> None:
        """Test that inputs with different time names raise a ValueError"""
        df = dataframe_to_timeframe(pl.DataFrame({"a": [1, 2, 3]})).df
        tf1 = ts.TimeFrame(df, "time", resolution="PT1H", periodicity="PT1H")
        tf2 = ts.TimeFrame(df.rename({"time": "timestamp"}), "timestamp", resolution="PT1H", periodicity="PT1H")

        with pytest.raises(ValueError):
            merge_multiple_timeframes([tf1, tf2])

    def test_merge_diff_resolutions_raises(self) -> None:
        """Test that inputs with different resolutions raise a ValueError"""
        df = dataframe_to_timeframe(pl.DataFrame({"a": [1, 2, 3]})).df
        tf1 = ts.TimeFrame(df, "time", resolution="PT1H", periodicity="PT1H")
        tf2 = ts.TimeFrame(df, "time", resolution="PT30M", periodicity="PT1H")

        with pytest.raises(ValueError):
            merge_multiple_timeframes([tf1, tf2])

    def test_merge_diff_periodicities_raises(self) -> None:
        """Test that inputs with different periodicities raise a ValueError"""
        hourly = dataframe_to_timeframe(pl.DataFrame({"a": [1, 2, 3]})).df
        two_hourly = pl.DataFrame(
            {
                "time": [datetime(2025, 1, 1) + timedelta(hours=2 * step) for step in range(3)],
                "b": [10, 20, 30],
            }
        )
        tf1 = ts.TimeFrame(hourly, "time", resolution="PT1H", periodicity="PT1H")
        tf2 = ts.TimeFrame(two_hourly, "time", resolution="PT1H", periodicity="PT2H")

        with pytest.raises(ValueError):
            merge_multiple_timeframes([tf1, tf2])

    def test_merge_diff_time_anchors_raises(self) -> None:
        """Test that inputs with different time anchors raise a ValueError"""
        df = dataframe_to_timeframe(pl.DataFrame({"a": [1, 2, 3]})).df
        tf1 = ts.TimeFrame(df, "time", resolution="PT1H", periodicity="PT1H", time_anchor="start")
        tf2 = ts.TimeFrame(df, "time", resolution="PT1H", periodicity="PT1H", time_anchor="end")

        with pytest.raises(ValueError):
            merge_multiple_timeframes([tf1, tf2])
