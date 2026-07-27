from datetime import datetime, timedelta
from unittest.mock import MagicMock

import polars as pl
import pytest
import time_stream as ts
from polars.testing import assert_series_equal
from tests.utils.data_creation import create_timeframe

from dritimeseriesprocessor.models.domain_models.processing_config import DataProcessingMethodConfig
from dritimeseriesprocessor.models.domain_models.time_series_container import TimeSeriesContainer
from dritimeseriesprocessor.operations.operation_pipeline import OperationPipeline
from dritimeseriesprocessor.operations.quality_control.qc_pipeline import QCPipeline


@pytest.fixture
def mock_timeframe() -> MagicMock:
    """Create a mock TimeFrame."""
    tf = MagicMock(spec=ts.TimeFrame)
    tf.metadata = {"column_name": "value"}
    tf.with_df.return_value = tf
    return tf


class TestGetFlagColumn:
    def test_get_qc_flag_column(self) -> None:
        """Test that correct flag column name is returned."""
        pipeline = QCPipeline({})
        result = pipeline.get_flag_column("temperature")
        assert result == "temperature_QC_FLAG"


class TestComputeFlagMask:
    def test_mask(self) -> None:
        """Test that compute_flag_mask returns the result TimeFrame directly."""
        pipeline = QCPipeline({})

        df = pl.DataFrame({"__qc_result_test": [1, 2, 3]})

        original = MagicMock(spec=ts.TimeFrame)
        result = MagicMock(spec=ts.TimeFrame)
        result.df = df

        mask = pipeline.compute_flag_mask(original, result, "test")
        assert_series_equal(mask, pl.Series("__qc_result_test", [1, 2, 3]))


class TestApply:
    def test_returns_method_result(self) -> None:
        """Test that apply returns a TimeFrame"""
        config = DataProcessingMethodConfig(method="range", params={"lt": 0, "gt": 100})
        tf = create_timeframe([1.0, 2.0, 3.0], column_name="value")

        pipeline = QCPipeline({})
        result = pipeline.apply(tf, config, {})

        assert isinstance(result, ts.TimeFrame)

    def test_drops_the_temporary_qc_result_column(self) -> None:
        """Test that the column holding the QC check result is not left on the returned TimeFrame"""
        config = DataProcessingMethodConfig(method="range", params={"lt": 0, "gt": 100})
        tf = create_timeframe([1.0, 2.0, 3.0], column_name="value")

        pipeline = QCPipeline({})
        result = pipeline.apply(tf, config, {})

        assert QCPipeline.get_qc_result_column("value") not in result.df.columns


class Test1minTsExtent:
    """Tests for the case where a dataframe has a different row count to another dataframe in the process.

    Reproduces a bug (FPM-1188) where a precip dataset built by aggregating 1-minute data to 30 minutes can end up one
    row longer than a 30-minute dependent dataset, if the 1-minute data extends past the last complete 30-minute step.
    `QCPipeline.apply` attaches the `dep_ts` QC result onto the frame being processed with a positional `with_columns`,
    so any row count mismatch raises a `ShapeError` instead of aligning the two frames by time.
    """

    @staticmethod
    def _make_padded_timeframe(
        times: list[datetime], column_name: str, values: list[float], periodicity: str
    ) -> ts.TimeFrame:
        df = pl.DataFrame({"time": times, column_name: values})
        return (
            ts.TimeFrame(df=df, time_name="time", resolution=periodicity, periodicity=periodicity, time_anchor="start")
            .with_metadata({"column_name": column_name})
            .pad()
        )

    def test_dep_ts_frame_one_row_shorter(self) -> None:
        """Tests that a 1-minute aggregation extending past the dep_ts frame's extent does not cause an error."""
        start = datetime(2025, 1, 1)

        # 1-minute data: 30 complete half-hour buckets, plus 5 minutes of a 31st (partial) bucket
        minute_count = 30 * 30 + 5
        precip_1min = self._make_padded_timeframe(
            [start + timedelta(minutes=i) for i in range(minute_count)], "PRECIP", [0.1] * minute_count, "PT1M"
        )
        precip_30min = precip_1min.aggregate(
            aggregation_period=ts.Period.of_iso_duration("PT30M"),
            aggregation_function="sum",
            aggregation_time_anchor="start",
            columns="PRECIP",
        )
        precip_30min = precip_30min.with_df(precip_30min.df.rename({"sum_PRECIP": "PRECIP"})).with_metadata(
            {"column_name": "PRECIP"}
        )

        # Example battery dataset loaded (and padded) at 30-minute periodicity, ending at the last complete bucket -
        # one row fewer than the precip aggregation above.
        battery_30min = self._make_padded_timeframe(
            [start + timedelta(minutes=30 * i) for i in range(30)], "BATTERY_V", [12.5] * 30, "PT30M"
        )

        # Now use both of these together in a QC run
        dep_container = MagicMock(spec=TimeSeriesContainer)
        dep_container.data = battery_30min

        config = DataProcessingMethodConfig(method="battery_v", params={"lt": 11.0, "dep_ts": "battery-ts-id"})
        pipeline = QCPipeline({})

        pipeline.apply(precip_30min, config, {"battery-ts-id": dep_container})


class TestRun:
    def _make_container(self) -> MagicMock:
        """Create a container that reports it has flagging configured."""
        container = MagicMock(spec=TimeSeriesContainer)
        container.has_flags.return_value = True
        return container

    def test_removes_flagged_data_when_remove_flagged_true(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that remove_flagged_data is called when remove_flagged is True and the dataset has flags."""
        qc_result = MagicMock(spec=ts.TimeFrame)
        monkeypatch.setattr(OperationPipeline, "run", lambda self, container, repo, config: qc_result)

        pipeline = QCPipeline({})
        removed = MagicMock(spec=ts.TimeFrame)
        pipeline.remove_flagged_data = MagicMock(return_value=removed)  # type: ignore[method-assign]

        result = pipeline.run(self._make_container(), {}, MagicMock(), remove_flagged=True)

        pipeline.remove_flagged_data.assert_called_once_with(qc_result)
        assert result is removed

    def test_keeps_flagged_data_when_remove_flagged_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that remove_flagged_data is not called when remove_flagged is False."""
        qc_result = MagicMock(spec=ts.TimeFrame)
        monkeypatch.setattr(OperationPipeline, "run", lambda self, container, repo, config: qc_result)

        pipeline = QCPipeline({})
        pipeline.remove_flagged_data = MagicMock()  # type: ignore[method-assign]

        result = pipeline.run(self._make_container(), {}, MagicMock(), remove_flagged=False)

        pipeline.remove_flagged_data.assert_not_called()
        assert result is qc_result


class TestCoreFlagUpdater:
    def test_calls_update_qc_core_flags(self, mock_timeframe: MagicMock, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that update_quality_control_core_flags is called."""
        mock_method = MagicMock(return_value=MagicMock(spec=ts.TimeFrame))
        monkeypatch.setattr(
            "dritimeseriesprocessor.operations.quality_control.qc_pipeline.update_quality_control_core_flags",
            mock_method,
        )

        pipeline = QCPipeline({})
        pipeline.core_flag_updater(mock_timeframe)
        mock_method.assert_called_once_with(mock_timeframe)


class TestRemoveFlaggedData:
    def _make_qc_timeframe(self, values: list, flags: list, col: str = "value") -> ts.TimeFrame:
        tf = create_timeframe(values, column_name=col)
        tf = tf.with_metadata({"column_name": col})
        tf.register_flag_system("qc_flags", {"range": 1})
        tf.init_flag_column("qc_flags", f"{col}_QC_FLAG")
        flag_col = f"{col}_QC_FLAG"
        for i, val in enumerate(flags):
            if val > 0:
                tf.add_flag(flag_col, "range", pl.Series([j == i for j in range(len(flags))]))
        return tf

    def test_nulls_values_where_flag_is_nonzero(self) -> None:
        """Tests that values are set to null where the QC flag is greater than zero."""
        tf = self._make_qc_timeframe(values=[1.0, 2.0, 3.0], flags=[0, 1, 0])

        result = QCPipeline.remove_flagged_data(tf)

        col = result.df["value"].to_list()
        assert col[0] == 1.0
        assert col[1] is None
        assert col[2] == 3.0

    def test_leaves_values_untouched_when_all_flags_zero(self) -> None:
        """Tests that no values are removed when all QC flags are zero."""
        tf = self._make_qc_timeframe(values=[1.0, 2.0, 3.0], flags=[0, 0, 0])

        result = QCPipeline.remove_flagged_data(tf)

        assert result.df["value"].to_list() == [1.0, 2.0, 3.0]

    def test_nulls_all_values_when_all_flags_nonzero(self) -> None:
        """Tests that all values are set to null when every row has a QC flag."""
        tf = self._make_qc_timeframe(values=[1.0, 2.0, 3.0], flags=[1, 1, 1])

        result = QCPipeline.remove_flagged_data(tf)

        assert all(v is None for v in result.df["value"].to_list())
