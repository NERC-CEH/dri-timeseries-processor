from unittest.mock import MagicMock, patch

import polars as pl
import pytest
import time_stream as ts
from polars.testing import assert_series_equal

from dritimeseriesprocessor.models.domain_models.processing_config import (
    DataProcessingConfig,
    DataProcessingMethodConfig,
)
from dritimeseriesprocessor.models.domain_models.time_series_container import TimeSeriesContainer
from dritimeseriesprocessor.operations.quality_control.qc_methods import QcMethod
from dritimeseriesprocessor.operations.quality_control.qc_pipeline import QCPipeline
from dritimeseriesprocessor.utils.enums import ConfigurationType


@pytest.fixture
def mock_timeframe() -> MagicMock:
    """Create a mock TimeFrame."""
    tf = MagicMock(spec=ts.TimeFrame)
    tf.metadata = {"column_name": "value"}
    tf.with_df.return_value = tf
    return tf


@pytest.fixture
def mock_container() -> MagicMock:
    """Create a mock TimeSeriesContainer with correction configs."""
    container = MagicMock(spec=TimeSeriesContainer)

    method_config = MagicMock(spec=DataProcessingMethodConfig)
    method_config.method = "range"
    method_config.params = {"lt": 0, "gt": 100}

    proc_config = MagicMock(spec=DataProcessingConfig)
    proc_config.method_configs = [method_config]
    proc_config.config_type = ConfigurationType.QUALITY_CONTROL

    container.qc_configs = {proc_config}
    return container


class TestGetConfigs:
    def test_get_qc_configs(self, mock_container: MagicMock) -> None:
        """Test that infill configs are extracted from container."""
        pipeline = QCPipeline()
        result = pipeline.get_configs(mock_container)
        assert result == mock_container.qc_configs

    def test_empty_infill_configs(self) -> None:
        """Test that empty set is returned when no infill configs."""
        pipeline = QCPipeline()
        container = MagicMock(spec=TimeSeriesContainer)
        container.qc_configs = set()

        result = pipeline.get_configs(container)

        assert result == set()


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
