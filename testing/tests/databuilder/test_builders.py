import datetime
from pathlib import Path
from typing import Any
from unittest import mock
from unittest.mock import patch

import pandas as pd
import pytest

from databuilder import utils
from databuilder.builders import ParquetBuilder
from databuilder.enums import Operator
from testing.utils.base_test_helper import BaseTestHelper

DEFAULT_PARQUET_PATH = "dataset=LIVE_PRECIP_1MIN/site=BUNNY/date=2024-03-01/data.parquet"


def construct_target(temp_dir: Path, parquet_path: str = DEFAULT_PARQUET_PATH) -> Path:
    utils.initialise_directory(temp_dir)

    parquet_path = "dataset=LIVE_PRECIP_1MIN/site=BUNNY/date=2024-03-01/data.parquet"
    return temp_dir.joinpath(parquet_path)


@pytest.fixture
def target(base_test_helper: BaseTestHelper) -> str:
    utils.initialise_directory(base_test_helper.temp_dir)

    parquet_path = "dataset=LIVE_PRECIP_1MIN/site=BUNNY/date=2024-03-01/data.parquet"
    return base_test_helper.temp_dir.joinpath(parquet_path)


@pytest.fixture
def builder(target: str) -> ParquetBuilder:
    return ParquetBuilder(target)


class TestParquetBuilderMethods:
    def test_class_instantiated(self, builder: ParquetBuilder) -> None:
        """Tests that the class is properly instantiated"""
        assert isinstance(builder.target, Path)
        assert isinstance(builder._output, Path)
        assert isinstance(builder._dataframe, pd.DataFrame)

        assert builder.target == builder._output

    def test_output_set(self, target: str) -> None:
        """Tests that the output parameter is set"""
        output = "/a/real/path"
        builder = ParquetBuilder(target, output)

        assert isinstance(builder._output, Path)
        assert builder._output == Path(output)

    def test_error_if_target_not_found(self) -> None:
        """Test that an error is raised if the target file does not exist"""

        target = "/totally/not/a/real/path"

        with pytest.raises(FileNotFoundError):
            ParquetBuilder(target)

    def test_reset(self, builder: ParquetBuilder) -> None:
        """Tests that the builder output can be reset"""
        assert builder._dataframe is not None

        builder.reset()

        assert not hasattr(builder, "_dataframe")
        assert not hasattr(builder, "target")
        assert not hasattr(builder, "output")


class TestTimeClearing:
    @pytest.mark.parametrize("operator", [1, 1.2, ">"])
    def test_error_if_non_enum_operator_used(self, operator: Any, builder: ParquetBuilder) -> None:
        """Test that a TypeError is raised unless the operator is passed as an Operator enum"""
        tm = datetime.time(hour=11)

        with pytest.raises(TypeError):
            builder.filter_by_time(tm, operator)

    @pytest.mark.parametrize("time", [1, 1.2, "10:20"])
    def test_error_if_non_datetime_received(
        self,
        builder: ParquetBuilder,
        time: Any,
    ) -> None:
        """Test that a TypeError is raised unless the operator is passed as an Operator enum"""
        with pytest.raises(TypeError):
            builder.filter_by_time(time, Operator.GREATER_THAN)

    def test_time_filter_gt(self, builder: ParquetBuilder) -> None:
        """Tests that method removes values not greater than the specified time"""
        tm = datetime.time(hour=11)
        operator = Operator.GREATER_THAN

        builder.filter_by_time(tm, operator)
        assert len(builder._dataframe) == 779

        df = builder._dataframe.query(f"time.dt.time <= @pd.Timestamp('{tm}').time()")
        assert df.empty

        df = builder._dataframe.query(f"time.dt.time {operator} @pd.Timestamp('{tm}').time()")
        assert len(builder._dataframe) == 779

    def test_time_filter_ge(self, builder: ParquetBuilder) -> None:
        """Tests that method removes values not greater than or equal to the specified time"""

        tm = datetime.time(hour=17, minute=14)
        operator = Operator.GREATER_THAN_EQUAL

        builder.filter_by_time(tm, operator)
        assert builder._dataframe.shape == (406, 14)

        df = builder._dataframe.query(f"time.dt.time < @pd.Timestamp('{tm}').time()")
        assert df.empty

        df = builder._dataframe.query(f"time.dt.time {operator} @pd.Timestamp('{tm}').time()")
        assert df.shape == (406, 14)

    def test_time_filter_eq(self, builder: ParquetBuilder) -> None:
        """Tests that method removes values not equal to the specified time"""

        tm = datetime.time(hour=17, minute=14)
        operator = Operator.EQUAL

        builder.filter_by_time(tm, operator)
        assert builder._dataframe.shape == (1, 14)

        df = builder._dataframe.query(f"time.dt.time != @pd.Timestamp('{tm}').time()")
        assert df.empty

        df = builder._dataframe.query(f"time.dt.time {operator} @pd.Timestamp('{tm}').time()")
        assert builder._dataframe.shape == (1, 14)

    def test_time_filter_lt(self, builder: ParquetBuilder) -> None:
        """Tests that method removes values not less than the specified time"""

        tm = datetime.time(hour=12, minute=14, second=36)
        operator = Operator.LESS_THAN

        builder.filter_by_time(tm, operator)
        assert builder._dataframe.shape == (735, 14)

        df = builder._dataframe.query(f"time.dt.time >= @pd.Timestamp('{tm}').time()")
        assert df.empty

        df = builder._dataframe.query(f"time.dt.time {operator} @pd.Timestamp('{tm}').time()")
        assert df.shape == (735, 14)

    def test_time_filter_le(self, builder: ParquetBuilder) -> None:
        """Tests that method removes values not less than or equal to the specified time"""

        tm = datetime.time(hour=23, minute=14, second=36)
        operator = Operator.LESS_THAN_EQUAL

        builder.filter_by_time(tm, operator)
        assert builder._dataframe.shape == (1395, 14)

        df = builder._dataframe.query(f"time.dt.time > @pd.Timestamp('{tm}').time()")
        assert df.empty

        df = builder._dataframe.query(f"time.dt.time {operator} @pd.Timestamp('{tm}').time()")
        assert df.shape == (1395, 14)


class TestPercentageRowRemoval:
    @pytest.mark.parametrize("percent", [-1, -1.2, 101, "1000"])
    def test_bad_percentage_error(self, percent: Any, builder: ParquetBuilder) -> None:
        """Tests that an error is raised for bad percentage values"""

        with pytest.raises(ValueError):
            builder.clear_percentage_of_rows(percent)

    @pytest.mark.parametrize("percent", [0, 10.5, 30, 75.9, 99.9, 100])
    def test_rows_removed(self, percent: Any, builder: ParquetBuilder) -> None:
        size_before = builder._dataframe.shape[0]
        assert size_before > 0

        acceptable_diff = size_before * 0.005
        expected = size_before * (1 - (percent / 100))

        builder.clear_percentage_of_rows(percent)

        size_after = builder._dataframe.shape[0]

        assert pytest.approx(size_after, abs=acceptable_diff) == pytest.approx(expected, abs=acceptable_diff)


class TestPercentageCellRemoval:
    excluded_columns = ["time", "SITE_ID", "RECORD"]

    @pytest.mark.parametrize("percent", [-1, -1.2, 101, "1000"])
    def test_bad_percentage_error(self, percent: Any, builder: ParquetBuilder) -> None:
        """Tests that an error is raised for bad percentage values"""
        with pytest.raises(ValueError):
            builder.set_random_cells_to_null(percent)

    @pytest.mark.parametrize("percent", [0, 10.5, 30, 75.9, 99.9, 100])
    def test_cells_removed(self, percent: Any, builder: ParquetBuilder) -> None:
        cols = [col for col in builder._dataframe.columns if col not in self.excluded_columns]

        n_rows = builder._dataframe.shape[0]
        assert n_rows != 0

        n_nan = [builder._dataframe[col].isna().sum() for col in cols]

        builder.set_random_cells_to_null(percent, exclude=self.excluded_columns)

        for col, nan_before in zip(cols, n_nan):
            expected = (n_rows - nan_before) * (percent / 100)

            size_after = builder._dataframe[col].isna().sum()
            assert size_after >= expected


class TestBuilderWriting:
    def test_output_written(self, builder: ParquetBuilder) -> None:
        """Tests that the builder output is written to file"""
        original_df = builder._dataframe.copy()

        builder.clear_percentage_of_rows(50)

        builder.write_output()

        output_df = pd.read_parquet(builder._output)

        assert not original_df.equals(output_df)

    def test_output_written_different_from_target_dir_exists(
        self, base_test_helper: BaseTestHelper, target: str
    ) -> None:
        """Tests that output is written to an existing directory but different filename"""
        output = base_test_helper.temp_dir.joinpath("new-file.parquet")
        builder = ParquetBuilder(target, output)

        assert not output.exists(), "Output file should not exist at test start."
        builder.write_output()
        assert output.exists()

        new_df = pd.read_parquet(output)

        assert builder._dataframe.equals(new_df)

    def test_output_written_to_non_existing_directory_ok(self, base_test_helper: BaseTestHelper, target: str) -> None:
        """Tests that output writes suceessfully to non-existing directory
        if the `new_dir_ok` fkag is set as True"""
        output = base_test_helper.temp_dir.joinpath("a", "new", "file.parquet")
        builder = ParquetBuilder(target, output)

        assert not output.exists(), "Output file should not exist at test start."
        assert not output.parent.is_dir(), "Output directory should not exist"

        builder.write_output(new_dir_ok=True)
        assert output.exists()

        new_df = pd.read_parquet(output)

        assert builder._dataframe.equals(new_df)

    def test_output_written_to_non_existing_directory_error(
        self, base_test_helper: BaseTestHelper, target: str
    ) -> None:
        """Tests error is raised if output directory doesn't exist and if the `new_dir_ok` fkag is set as False"""
        output = base_test_helper.temp_dir.joinpath("a", "new", "file.parquet")
        builder = ParquetBuilder(target, output)

        with pytest.raises(NotADirectoryError):
            builder.write_output()


class TestBuilderInvocationMethod:
    @pytest.mark.parametrize(
        "p_row,p_cell,b_time,a_time",
        [
            [10, None, None, None],
            [None, 30, None, None],
            [10, 45, datetime.time(11), None],
            [None, None, None, datetime.time(9, 32)],
            [15.5, 79, datetime.time(18, 42), datetime.time(9, 32)],
        ],
    )
    @patch("databuilder.builders.ParquetBuilder.filter_by_time")
    @patch("databuilder.builders.ParquetBuilder.set_random_cells_to_null")
    @patch("databuilder.builders.ParquetBuilder.clear_percentage_of_rows")
    def test_build_methods_called(
        self,
        row_mock: mock.MagicMock,
        cell_mock: mock.MagicMock,
        time_mock: mock.MagicMock,
        p_row: int | float | None,
        p_cell: int | float | None,
        b_time: datetime.time | None,
        a_time: datetime.time | None,
        builder: ParquetBuilder,
    ) -> None:
        """Tests that the build methods are called"""

        builder.build_all(p_row, p_cell, b_time, a_time)

        if p_row:
            row_mock.assert_called_once_with(p_row)
        else:
            row_mock.assert_not_called()

        if p_cell:
            cell_mock.assert_called_once_with(p_cell, exclude=None)
        else:
            cell_mock.assert_not_called()

        if not b_time and not a_time:
            time_mock.assert_not_called()
        elif b_time and a_time:
            time_mock.assert_has_calls(
                [mock.call(b_time, Operator.GREATER_THAN_EQUAL), mock.call(a_time, Operator.LESS_THAN_EQUAL)]
            )
        elif b_time:
            time_mock.assert_called_with(b_time, Operator.GREATER_THAN_EQUAL)
        elif a_time:
            time_mock.assert_called_with(a_time, Operator.LESS_THAN_EQUAL)

    @pytest.mark.parametrize(
        "p_row,p_cell,b_time,a_time",
        [
            [10, None, None, None],
            [None, 30, None, None],
            [10, 45, datetime.time(11), None],
            [None, None, None, datetime.time(9, 32)],
            [15.5, 79, datetime.time(18, 42), datetime.time(9, 32)],
        ],
    )
    @patch("databuilder.builders.ParquetBuilder.filter_by_time")
    @patch("databuilder.builders.ParquetBuilder.set_random_cells_to_null")
    @patch("databuilder.builders.ParquetBuilder.clear_percentage_of_rows")
    def test_build_methods_called_protected_columns(
        self,
        row_mock: mock.MagicMock,
        cell_mock: mock.MagicMock,
        time_mock: mock.MagicMock,
        p_row: int | float | None,
        p_cell: int | float | None,
        b_time: datetime.time | None,
        a_time: datetime.time | None,
        builder: ParquetBuilder,
    ) -> None:
        """Tests that the build methods are called"""
        protected_columns = ["time", "SITE_ID"]

        builder.build_all(p_row, p_cell, b_time, a_time, protected_columns=protected_columns)

        if p_row:
            row_mock.assert_called_once_with(p_row)
        else:
            row_mock.assert_not_called()

        if p_cell:
            cell_mock.assert_called_once_with(p_cell, exclude=protected_columns)
        else:
            cell_mock.assert_not_called()

        if not b_time and not a_time:
            time_mock.assert_not_called()
        elif b_time and a_time:
            time_mock.assert_has_calls(
                [mock.call(b_time, Operator.GREATER_THAN_EQUAL), mock.call(a_time, Operator.LESS_THAN_EQUAL)]
            )
        elif b_time:
            time_mock.assert_called_with(b_time, Operator.GREATER_THAN_EQUAL)
        elif a_time:
            time_mock.assert_called_with(a_time, Operator.LESS_THAN_EQUAL)
