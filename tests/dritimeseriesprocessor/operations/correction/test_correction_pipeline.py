from unittest.mock import MagicMock, patch

import polars as pl
import pytest
import time_stream as ts
from polars.testing import assert_series_equal

from dritimeseriesprocessor.models.domain_models.processing_config import DataProcessingMethodConfig
from dritimeseriesprocessor.operations.correction.correction_methods import CorrectionMethod
from dritimeseriesprocessor.operations.correction.correction_pipeline import CorrectionPipeline
from dritimeseriesprocessor.operations.flags.flag_methods import update_corrections_core_flags
from utils.data_creation import create_timeframe


@pytest.fixture
def mock_timeframe() -> MagicMock:
    """Create a mock TimeFrame."""
    tf = MagicMock(spec=ts.TimeFrame)
    tf.metadata = {"column_name": "value"}
    tf.df = pl.DataFrame({"time": [1, 2, 3], "value": [10.0, 20.0, 30.0]})
    return tf


class TestGetFlagColumn:
    def test_get_correction_flag_column(self) -> None:
        """Test that correct flag column name is returned."""
        pipeline = CorrectionPipeline({})
        result = pipeline.get_flag_column("temperature")
        assert result == "temperature_CORRS_FLAG"


class TestComputeFlagMask:
    @pytest.mark.parametrize(
        "before, after, expected",
        [
            pytest.param([10.0, 20.0, 30.0], [15.0, 25.0, 35.0], [True, True, True], id="all different"),
            pytest.param([None, 10.0, 20.0], [5.0, 10.0, None], [True, False, True], id="null different"),
            pytest.param([10.0, 20.0, 30.0], [10.0, 20.0, 30.0], [False, False, False], id="all same"),
            pytest.param([10.0, 20.0, None], [10.0, 20.0, None], [False, False, False], id="all same with null"),
            pytest.param([None, None, None], [None, None, None], [False, False, False], id="all null"),
        ],
    )
    def test_mask(self, before: list, after: list, expected: list) -> None:
        """Test that mask identifies when values are changed."""
        pipeline = CorrectionPipeline({})

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
        with patch.object(CorrectionMethod, "get") as mock_get:
            mock_method = MagicMock()
            mock_method.run.return_value = expected_result
            mock_get.return_value = mock_method

            pipeline = CorrectionPipeline({})
            result = pipeline.apply(mock_timeframe, config, {})
            assert isinstance(result, ts.TimeFrame)


class TestUncoveredTimeValues:
    def test_row_with_no_dependency_value_is_flagged_unsuccessful(self) -> None:
        """Tests that a row the dependency doesn't cover is flagged as an unsuccessful correction, not as corrected."""
        core_flags = {"unchecked": 1, "corrected": 4, "unsuccessful_correction": 64}

        pa = create_timeframe([1007.504, 1007.391, 1007.359], "pa")
        pa.register_flag_system("core", core_flags)
        pa.init_flag_column("core", "pa_CORE_FLAG")
        pa.register_flag_system("corrs", {"pa_corr": 2})
        pa.init_flag_column("corrs", "pa_CORRS_FLAG")

        # ta covers one time value fewer than pa, so pa's last row has nothing to correct against
        ta = create_timeframe([12.25, 12.49], "ta")
        config = DataProcessingMethodConfig(
            method="pa_corr", params={"correction_factor": -5.1, "ta": ta, "altitude": 74.0}
        )

        pipeline = CorrectionPipeline({"core": core_flags})
        result = update_corrections_core_flags(pipeline.apply(pa, config, {}))

        # The correction was attempted on every row, so all three carry the corrections flag
        assert result.df["pa_CORRS_FLAG"].to_list() == [2, 2, 2]
        assert result.df["pa_CORE_FLAG"].to_list() == [4, 4, 64]


class TestCoreFlagUpdater:
    def test_calls_update_corrections_core_flags(
        self, mock_timeframe: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that update_corrections_core_flags is called."""
        mock_method = MagicMock(return_value=MagicMock(spec=ts.TimeFrame))
        monkeypatch.setattr(
            "dritimeseriesprocessor.operations.correction.correction_pipeline.update_corrections_core_flags",
            mock_method,
        )

        pipeline = CorrectionPipeline({})
        pipeline.core_flag_updater(mock_timeframe)
        mock_method.assert_called_once_with(mock_timeframe)
