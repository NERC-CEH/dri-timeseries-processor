from datetime import datetime

import polars as pl
import pytest
from polars.exceptions import ColumnNotFoundError
from polars.testing import assert_frame_equal

from dritimeseriesprocessor.utils.polars_utils import (
    join_time_intervals,
    merge_dataframes,
    merge_multiple,
    missing_expr,
    not_missing_expr,
    split_by_date,
)


class TestSplitByDate:
    @pytest.mark.parametrize(
        "df, expected",
        [
            pytest.param(
                pl.DataFrame(
                    {
                        "t": [datetime(2024, 1, 1, 10, 0), datetime(2024, 1, 1, 11, 0), datetime(2024, 1, 2, 9, 0)],
                        "value": [1, 2, 3],
                    }
                ),
                (
                    pl.DataFrame({"t": [datetime(2024, 1, 1, 10, 0), datetime(2024, 1, 1, 11, 0)], "value": [1, 2]}),
                    pl.DataFrame({"t": [datetime(2024, 1, 2, 9, 0)], "value": [3]}),
                ),
                id="simple dataframe",
            ),
            pytest.param(
                pl.DataFrame(
                    {
                        "t": [datetime(2024, 5, 1), datetime(2024, 1, 1), datetime(2025, 11, 2)],
                        "value": [1, 2, 3],
                    }
                ),
                (
                    pl.DataFrame({"t": [datetime(2024, 1, 1)], "value": [2]}),
                    pl.DataFrame({"t": [datetime(2024, 5, 1)], "value": [1]}),
                    pl.DataFrame({"t": [datetime(2025, 11, 2)], "value": [3]}),
                ),
                id="unsorted input times",
            ),
        ],
    )
    def test_split_by_date(self, df: pl.DataFrame, expected: tuple[pl.DataFrame, ...]) -> None:
        """Test we get expected split dataframes based on dates."""
        result = split_by_date(df, "t")

        assert len(result) == len(expected)
        for idx, (dt, df_split) in enumerate(result):
            assert_frame_equal(df_split, expected[idx])

    def test_split_by_date_empty_df(self) -> None:
        df = pl.DataFrame()
        result = split_by_date(df, "t")
        assert result == []

    def test_split_by_date_empty_cols(self) -> None:
        df = pl.DataFrame({"t": [], "value": []})
        result = split_by_date(df, "t")
        assert result == []

    def test_split_by_date_missing_time_col(self) -> None:
        df = pl.DataFrame({"a": [1, 2]})
        with pytest.raises(ColumnNotFoundError):
            split_by_date(df, "t")


class TestMergeDataframes:
    def test_merge_dataframes_same_join(self) -> None:
        """Test merging dataframes with the same join column."""
        df1 = pl.DataFrame({"join": [1, 2], "a": [10, 20]})
        df2 = pl.DataFrame({"join": [1, 2], "b": [100, 200]})
        expected = pl.DataFrame({"join": [1, 2], "a": [10, 20], "b": [100, 200]})

        result = merge_dataframes(df1, df2, "join")
        assert_frame_equal(result, expected, check_column_order=False)

    def test_merge_dataframes_overlapping_join(self) -> None:
        """Test merging dataframes with overlapping join column values."""
        df1 = pl.DataFrame({"join": [1, 2], "a": [10, 20]})
        df2 = pl.DataFrame({"join": [2, 3], "b": [100, 200]})
        expected = pl.DataFrame({"join": [1, 2, 3], "a": [10, 20, None], "b": [None, 100, 200]})

        result = merge_dataframes(df1, df2, "join")
        assert_frame_equal(result, expected, check_column_order=False)

    def test_merge_dataframes_different_join(self) -> None:
        """Test merging dataframes with all different join column values."""
        df1 = pl.DataFrame({"join": [1, 2], "a": [10, 20]})
        df2 = pl.DataFrame({"join": [3, 4], "b": [100, 200]})
        expected = pl.DataFrame({"join": [1, 2, 3, 4], "a": [10, 20, None, None], "b": [None, None, 100, 200]})

        result = merge_dataframes(df1, df2, "join")
        assert_frame_equal(result, expected, check_column_order=False)

    def test_merge_dataframes_overlapping_non_join_col(self) -> None:
        """Test merging dataframes with the same non-join columns."""
        df1 = pl.DataFrame({"join": [1, 2], "a": [10, 20]})
        df2 = pl.DataFrame({"join": [1, 2], "a": [100, 200]})
        expected = pl.DataFrame({"join": [1, 2], "a": [100, 200]})  # Will take last values joined

        result = merge_dataframes(df1, df2, "join")
        assert_frame_equal(result, expected, check_column_order=False)

    def test_merge_dataframes_missing_join_col(self) -> None:
        """Test error raise if one of the DataFrames doesn't contain the join column"""
        df1 = pl.DataFrame({"a": [10, 20]})
        df2 = pl.DataFrame({"join": [1, 2], "b": [100, 200]})

        with pytest.raises(ValueError):
            merge_dataframes(df1, df2, "join")

    def test_merge_dataframes_df1_empty(self) -> None:
        df1 = pl.DataFrame()
        df2 = pl.DataFrame({"join": [1, 2], "b": [100, 200]})
        expected = df2.clone()

        result = merge_dataframes(df1, df2, "join")
        assert_frame_equal(result, expected, check_column_order=False)

    def test_merge_dataframes_df2_empty(self) -> None:
        df1 = pl.DataFrame({"join": [1, 2], "a": [10, 20]})
        df2 = pl.DataFrame()
        expected = df1.clone()

        result = merge_dataframes(df1, df2, "join")
        assert_frame_equal(result, expected, check_column_order=False)

    def test_merge_dataframes_both_empty(self) -> None:
        df1 = pl.DataFrame()
        df2 = pl.DataFrame()
        expected = pl.DataFrame()

        result = merge_dataframes(df1, df2, "join")
        assert_frame_equal(result, expected, check_column_order=False)

    def test_merge_dataframes_empty_cols(self) -> None:
        df1 = pl.DataFrame({"join": [], "a": []})
        df2 = pl.DataFrame({"join": [], "b": []})
        expected = pl.DataFrame()

        result = merge_dataframes(df1, df2, "join")
        assert_frame_equal(result, expected, check_column_order=False)


class TestMissingExpr:
    def test_missing_expr(self) -> None:
        """Test the expression for detecting missing values."""
        expr = missing_expr("value")
        df = pl.DataFrame({"value": [10, None, 30, float("nan"), 50]}, strict=False)
        result = df.with_columns(expr.alias("is_missing"))
        assert result["is_missing"].to_list() == [False, True, False, True, False]


class TestNotMissingExpr:
    def test_not_missing_expr(self) -> None:
        """Test the expression for detecting non-missing values."""
        expr = not_missing_expr("value")
        df = pl.DataFrame({"value": [10, None, 30, float("nan"), 50]}, strict=False)
        result = df.with_columns(expr.alias("is_not_missing"))
        assert result["is_not_missing"].to_list() == [True, False, True, False, True]


class TestMergeMultiple:
    def test_merge_two(self) -> None:
        """Merge two DataFrames with matching rows."""
        df1 = pl.DataFrame({"id": [1, 2, 3], "a": [10, 20, 30]})
        df2 = pl.DataFrame({"id": [1, 2, 3], "b": [5, 10, 15]})

        result = merge_multiple([df1, df2], join_col="id")
        expected = pl.DataFrame({"id": [1, 2, 3], "a": [10, 20, 30], "b": [5, 10, 15]})

        assert_frame_equal(result, expected)

    def test_merge_two_offset(self) -> None:
        """Merge two DataFrames with overlapping join column values."""
        df1 = pl.DataFrame({"id": [1, 2, 3], "a": [10, 20, 30]})
        df2 = pl.DataFrame({"id": [2, 3, 4], "b": [5, 10, 15]})

        result = merge_multiple([df1, df2], join_col="id")
        expected = pl.DataFrame({"id": [1, 2, 3, 4], "a": [10, 20, 30, None], "b": [None, 5, 10, 15]})

        assert_frame_equal(result, expected, check_row_order=False)

    def test_merge_single(self) -> None:
        """Test that a single dataframe passes through"""
        df1 = pl.DataFrame({"id": [1, 2, 3], "a": [10, 20, 30]})
        result = merge_multiple([df1], join_col="id")
        assert_frame_equal(result, df1)

    def test_merge_multiple(self) -> None:
        """Merge multiple DataFrames"""
        df1 = pl.DataFrame({"id": [1, 2, 3], "a": [10, 20, 30]})
        df2 = pl.DataFrame({"id": [1, 2, 3], "b": [5, 10, 15]})
        df3 = pl.DataFrame({"id": [2, 3, 4], "c": [100, 200, 300]})
        df4 = pl.DataFrame({"id": [5, 6, 7], "d": [50, 100, 150]})

        result = merge_multiple([df1, df2, df3, df4], join_col="id")
        expected = pl.DataFrame(
            {
                "id": [1, 2, 3, 4, 5, 6, 7],
                "a": [10, 20, 30, None, None, None, None],
                "b": [5, 10, 15, None, None, None, None],
                "c": [None, 100, 200, 300, None, None, None],
                "d": [None, None, None, None, 50, 100, 150],
            }
        )

        assert_frame_equal(result, expected, check_row_order=False)


class TestJoinTimeIntervals:
    df = pl.DataFrame(
        {
            "time": [
                datetime(2019, 9, 10),
                datetime(2019, 9, 11),
                datetime(2019, 9, 12),
            ],
            "value": [1, 2, 3],
        }
    )

    def test_join_single_interval(self) -> None:
        intervals = [
            (datetime(2019, 9, 1), None, 2.1),
        ]
        expected = pl.DataFrame(
            {
                "time": [datetime(2019, 9, 10), datetime(2019, 9, 11), datetime(2019, 9, 12)],
                "value": [1, 2, 3],
                "interval_value": [2.1, 2.1, 2.1],
            }
        )
        result = join_time_intervals(intervals, self.df, "time", "interval_value")
        assert_frame_equal(result, expected)

    def test_join_multiple_intervals(self) -> None:
        intervals = [
            (datetime(2019, 9, 1), datetime(2019, 9, 11), 2.8),
            (datetime(2019, 9, 11), None, 2.1),
        ]
        expected = pl.DataFrame(
            {
                "time": [datetime(2019, 9, 10), datetime(2019, 9, 11), datetime(2019, 9, 12)],
                "value": [1, 2, 3],
                "interval_value": [2.8, 2.1, 2.1],
            }
        )
        result = join_time_intervals(intervals, self.df, "time", "interval_value")
        assert_frame_equal(result, expected)

    def test_join_interval_rows_before_first_interval_none(self) -> None:
        """Test that any rows in the parent df that are before any of the intervals are given a None value"""
        intervals = [
            (datetime(2019, 9, 11), None, 2.1),
        ]
        expected = pl.DataFrame(
            {
                "time": [datetime(2019, 9, 10), datetime(2019, 9, 11), datetime(2019, 9, 12)],
                "value": [1, 2, 3],
                "interval_value": [None, 2.1, 2.1],
            }
        )
        result = join_time_intervals(intervals, self.df, "time", "interval_value")
        assert_frame_equal(result, expected)

    def test_interval_gaps(self) -> None:
        intervals = [(datetime(2019, 9, 1), datetime(2019, 9, 10, 12), 2.1), (datetime(2019, 9, 11, 12), None, 2.1)]
        expected = pl.DataFrame(
            {
                "time": [datetime(2019, 9, 10), datetime(2019, 9, 11), datetime(2019, 9, 12)],
                "value": [1, 2, 3],
                "interval_value": [2.1, None, 2.1],
            }
        )
        result = join_time_intervals(intervals, self.df, "time", "interval_value")
        assert_frame_equal(result, expected)

    def test_end_before_start_raises(self) -> None:
        intervals = [
            (datetime(2019, 9, 30), datetime(2019, 9, 1), 1.0),
        ]
        with pytest.raises(ValueError):
            join_time_intervals(intervals, self.df, "time", "interval_value")

    def test_overlapping_intervals_raises(self) -> None:
        intervals = [
            (datetime(2019, 9, 1), datetime(2019, 9, 30), 1.0),
            (datetime(2019, 9, 29), datetime(2019, 10, 1), 2.0),
        ]
        with pytest.raises(ValueError):
            join_time_intervals(intervals, self.df, "time", "interval_value")

    def test_multiple_open_ended_raises(self) -> None:
        intervals = [(datetime(2019, 9, 1), None, 1.0), (datetime(2019, 9, 29), None, 2.0)]
        with pytest.raises(ValueError):
            join_time_intervals(intervals, self.df, "time", "interval_value")

    def test_open_ended_not_last_raises(self) -> None:
        intervals = [(datetime(2019, 9, 1), None, 1.0), (datetime(2019, 9, 29), datetime(2019, 10, 5), 2.0)]
        with pytest.raises(ValueError):
            join_time_intervals(intervals, self.df, "time", "interval_value")
