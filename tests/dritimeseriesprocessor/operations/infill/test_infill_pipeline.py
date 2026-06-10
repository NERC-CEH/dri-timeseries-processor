from unittest.mock import MagicMock, patch

import polars as pl
import pytest
import time_stream as ts
from polars.testing import assert_series_equal

from dritimeseriesprocessor.models.domain_models.processing_config import DataProcessingMethodConfig
from dritimeseriesprocessor.operations.infill.infill_methods import InfillMethod
from dritimeseriesprocessor.operations.infill.infill_pipeline import InfillPipeline


@pytest.fixture
def mock_timeframe() -> MagicMock:
    """Create a mock TimeFrame."""
    tf = MagicMock(spec=ts.TimeFrame)
    tf.metadata = {"column_name": "value"}
    tf.df = pl.DataFrame({"time": [1, 2, 3], "value": [10.0, 20.0, 30.0]})
    return tf


class TestGetFlagColumn:
    def test_get_infill_flag_column(self) -> None:
        """Test that correct flag column name is returned."""
        pipeline = InfillPipeline()
        result = pipeline.get_flag_column("temperature")
        assert result == "temperature_INFILL_FLAG"


class TestComputeFlagMask:
    @pytest.mark.parametrize(
        "before, after, expected",
        [
            pytest.param([None, None, None], [15.0, 25.0, 35.0], [True, True, True], id="all infilled"),
            pytest.param([None, 10.0, None], [5.0, 10.0, None], [True, False, False], id="some infilled"),
            pytest.param([10.0, 20.0, 30.0], [10.0, 20.0, 30.0], [False, False, False], id="all same"),
            pytest.param([10.0, 20.0, None], [10.0, 20.0, None], [False, False, False], id="all same with null"),
            pytest.param([None, None, None], [None, None, None], [False, False, False], id="all null"),
        ],
    )
    def test_mask(self, before: list, after: list, expected: list) -> None:
        """Test that mask identifies when values are changed."""
        pipeline = InfillPipeline()

        original = MagicMock(spec=ts.TimeFrame)
        original.df = pl.DataFrame({"value": before})
        result = MagicMock(spec=ts.TimeFrame)
        result.df = pl.DataFrame({"value": after})

        mask = pipeline.compute_flag_mask(original, result, "value")
        assert_series_equal(mask, pl.Series(expected), check_names=False)


class TestApply:
    def test_returns_method_result(self, mock_timeframe: MagicMock) -> None:
        """Test that apply returns a TimeFrame"""
        config = MagicMock(spec=DataProcessingMethodConfig)
        config.method = "add"
        config.params = {"correction_factor": 10}

        expected_result = mock_timeframe
        with patch.object(InfillMethod, "get") as mock_get:
            mock_method = MagicMock()
            mock_method.run.return_value = expected_result
            mock_get.return_value = mock_method

            pipeline = InfillPipeline()
            result = pipeline.apply(mock_timeframe, config, {})
            assert isinstance(result, ts.TimeFrame)


class TestCoreFlagUpdater:
    def test_calls_update_infill_core_flags(self, mock_timeframe: MagicMock, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that update_infill_core_flags is called."""
        mock_method = MagicMock(return_value=MagicMock(spec=ts.TimeFrame))
        monkeypatch.setattr(
            "dritimeseriesprocessor.operations.infill.infill_pipeline.update_infill_core_flags", mock_method
        )

        pipeline = InfillPipeline()
        pipeline.core_flag_updater(mock_timeframe)
        mock_method.assert_called_once_with(mock_timeframe)
