from unittest.mock import MagicMock, patch

import polars as pl
import pytest
import time_stream as ts
from polars.testing import assert_series_equal
from tests.utils.data_creation import create_timeframe

from dritimeseriesprocessor.models.domain_models.processing_config import DataProcessingMethodConfig
from dritimeseriesprocessor.operations.quality_control.qc_methods import QcMethod
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
        pipeline = QCPipeline()
        result = pipeline.get_flag_column("temperature")
        assert result == "temperature_QC_FLAG"


class TestComputeFlagMask:
    def test_mask(self) -> None:
        """Test that compute_flag_mask returns the result TimeFrame directly."""
        pipeline = QCPipeline()

        df = pl.DataFrame({"__qc_result_test": [1, 2, 3]})

        original = MagicMock(spec=ts.TimeFrame)
        result = MagicMock(spec=ts.TimeFrame)
        result.df = df

        mask = pipeline.compute_flag_mask(original, result, "test")
        assert_series_equal(mask, pl.Series("__qc_result_test", [1, 2, 3]))


class TestApply:
    def test_returns_method_result(self, mock_timeframe: MagicMock) -> None:
        """Test that apply returns a TimeFrame"""
        config = MagicMock(spec=DataProcessingMethodConfig)
        config.method = "range"
        config.params = {"lt": 0, "gt": 100}

        expected_result = MagicMock(spec=pl.Series)
        with patch.object(QcMethod, "get") as mock_get:
            mock_method = MagicMock()
            mock_method.run.return_value = expected_result
            mock_get.return_value = mock_method

            pipeline = QCPipeline()
            result = pipeline.apply(mock_timeframe, config, {})
            assert isinstance(result, ts.TimeFrame)


class TestCoreFlagUpdater:
    def test_calls_update_qc_core_flags(self, mock_timeframe: MagicMock, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that update_quality_control_core_flags is called."""
        mock_method = MagicMock(return_value=MagicMock(spec=ts.TimeFrame))
        monkeypatch.setattr(
            "dritimeseriesprocessor.operations.quality_control.qc_pipeline.update_quality_control_core_flags",
            mock_method,
        )

        pipeline = QCPipeline()
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
