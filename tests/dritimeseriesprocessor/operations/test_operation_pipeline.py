from typing import Iterable
from unittest.mock import MagicMock

import pytest
import time_stream as ts
from time_stream.exceptions import FlagSystemNotFoundError

from dritimeseriesprocessor.models.domain_models.processing_config import (
    DataProcessingConfig,
    DataProcessingMethodConfig,
)
from dritimeseriesprocessor.models.domain_models.time_series_container import TimeSeriesContainer
from dritimeseriesprocessor.operations.operation_pipeline import OperationPipeline
from dritimeseriesprocessor.utils.enums import OperationType


class MockOperationPipeline(OperationPipeline):
    """Implementation of OperationPipeline for testing."""

    def apply(self, tf: ts.TimeFrame, *args) -> ts.TimeFrame:
        return tf

    def get_configs(self, container: TimeSeriesContainer) -> Iterable[DataProcessingConfig]:
        return container.qc_configs

    def get_flag_column(self, column: str) -> str:
        return f"{column}_TEST_FLAG"

    def compute_flag_mask(self, *args) -> MagicMock:
        return MagicMock()

    def core_flag_updater(self, tf: ts.TimeFrame) -> ts.TimeFrame:
        return tf


@pytest.fixture
def mock_timeframe() -> MagicMock:
    """Create a mock TimeFrame with necessary attributes."""
    tf = MagicMock(spec=ts.TimeFrame)
    tf.metadata = {"column_name": "value"}
    tf.data_columns = ["value"]
    tf.flag_columns = []
    tf.copy.return_value = tf
    return tf


@pytest.fixture
def mock_container(mock_timeframe: MagicMock) -> MagicMock:
    """Create a mock TimeSeriesContainer."""
    container = MagicMock(spec=TimeSeriesContainer)
    container.data = mock_timeframe

    method_config = MagicMock(spec=DataProcessingMethodConfig)
    method_config.method = "test_method"

    proc_config = MagicMock(spec=DataProcessingConfig)
    proc_config.method_configs = [method_config]

    container.qc_configs = [proc_config]
    return container


class TestSortConfigs:
    def test_returns_configs_unchanged_by_default(self) -> None:
        """Test that default implementation returns configs unchanged."""
        pipeline = MockOperationPipeline(OperationType.QUALITY_CONTROL, "test_flags")
        configs = [MagicMock(id=1), MagicMock(id=2), MagicMock(id=3)]

        result = pipeline.sort_configs(configs)
        assert result == configs


class TestInitialiseFlagSystem:
    def test_registers_new_flag_system(self, mock_timeframe: MagicMock) -> None:
        """Test that flag system registration is called when it doesn't exist."""
        pipeline = MockOperationPipeline(OperationType.QUALITY_CONTROL, "test_flags")
        pipeline.registry = {"flag1": MagicMock(flag_value=1), "flag2": MagicMock(flag_value=2)}

        mock_timeframe.get_flag_system.side_effect = FlagSystemNotFoundError("Not found")

        pipeline._initialise_flag_system(mock_timeframe)
        mock_timeframe.register_flag_system.assert_called_once_with("test_flags", {"flag1": 1, "flag2": 2})

    def test_no_new_register(self, mock_timeframe: MagicMock) -> None:
        """Test that flag system registration is not called when it does exist."""
        pipeline = MockOperationPipeline(OperationType.QUALITY_CONTROL, "test_flags")
        pipeline.registry = {"flag1": MagicMock(flag_value=1), "flag2": MagicMock(flag_value=2)}

        mock_timeframe.get_flag_system.return_value = {"test_flags": "exist"}

        pipeline._initialise_flag_system(mock_timeframe)
        mock_timeframe.register_flag_system.assert_not_called()


class TestInitialiseFlagColumn:
    def test_initialises_new_flag_column(self, mock_timeframe: MagicMock) -> None:
        """Test that flag column registration is called when it doesn't exist."""
        pipeline = MockOperationPipeline(OperationType.QUALITY_CONTROL, "test_flags")

        pipeline._initialise_flag_column(mock_timeframe, "value")
        mock_timeframe.init_flag_column.assert_called_once_with("value", "test_flags", "value_TEST_FLAG")

    def test_no_new_register(self, mock_timeframe: MagicMock) -> None:
        """Test that flag column registration is not called when it does exist."""
        pipeline = MockOperationPipeline(OperationType.QUALITY_CONTROL, "test_flags")
        mock_timeframe.flag_columns = ["value_TEST_FLAG"]

        pipeline._initialise_flag_column(mock_timeframe, "value")
        mock_timeframe.init_flag_column.assert_not_called()


class TestRun:
    def test_copies_timeframe_from_container(self, mock_container: MagicMock, mock_timeframe: MagicMock) -> None:
        """Test that TimeFrame is copied from container."""
        pipeline = MockOperationPipeline(OperationType.QUALITY_CONTROL, "test_flags")
        pipeline.run(mock_container, {})
        mock_timeframe.copy.assert_called_once()

    def test_returns_updated_timeframe(self, mock_container: MagicMock, mock_timeframe: MagicMock) -> None:
        """Test that updated TimeFrame is returned."""
        pipeline = MockOperationPipeline(OperationType.QUALITY_CONTROL, "test_flags")
        updated_tf = MagicMock()
        pipeline.core_flag_updater = MagicMock(return_value=updated_tf)

        result = pipeline.run(mock_container, {})
        assert result is updated_tf
