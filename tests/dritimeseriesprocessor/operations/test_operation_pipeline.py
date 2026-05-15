from typing import Iterable
from unittest.mock import MagicMock

import pytest
import time_stream as ts
from polars.testing import assert_frame_equal
from tests.utils.data_creation import create_timeframe
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

    def apply(self, tf: ts.TimeFrame, *_, **__) -> ts.TimeFrame:
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
    container.time_column_name = "time"
    container.data = mock_timeframe

    method_config = MagicMock(spec=DataProcessingMethodConfig)
    method_config.method = "test_method"
    method_config.params = {}

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
        mock_timeframe.init_flag_column.assert_called_once_with("test_flags", "value_TEST_FLAG")

    def test_no_new_register(self, mock_timeframe: MagicMock) -> None:
        """Test that flag column registration is not called when it does exist."""
        pipeline = MockOperationPipeline(OperationType.QUALITY_CONTROL, "test_flags")
        mock_timeframe.flag_columns = ["value_TEST_FLAG"]

        pipeline._initialise_flag_column(mock_timeframe, "value")
        mock_timeframe.init_flag_column.assert_not_called()


class TestRun:
    def test_returns_updated_timeframe(self, mock_container: MagicMock, mock_timeframe: MagicMock) -> None:
        """Test that updated TimeFrame is returned."""
        pipeline = MockOperationPipeline(OperationType.QUALITY_CONTROL, "test_flags")
        updated_tf = MagicMock()
        pipeline.core_flag_updater = MagicMock(return_value=updated_tf)

        result = pipeline.run(mock_container, {})
        assert result is updated_tf.rename_time_column()


class TestApplyRounding:
    @pytest.mark.parametrize(
        "decimals, expected",
        [
            (1, [1.2, 2.3, 3.5]),
            (0, [1.0, 2.0, 3.0]),
            (None, [1.234, 2.345, 3.456]),
        ],
    )
    def test_apply_rounding(self, mock_container: MagicMock, decimals: int, expected: list) -> None:
        """Test that updated TimeFrame is returned."""
        tf = create_timeframe([1.234, 2.345, 3.456])

        config = MagicMock(spec=DataProcessingMethodConfig)
        config.method = "test_method"
        config.params = {"round": decimals}

        method_config = MagicMock(spec=DataProcessingConfig)
        method_config.method_configs = [config]

        mock_container.data = tf
        mock_container.qc_configs = [method_config]

        pipeline = MockOperationPipeline(OperationType.QUALITY_CONTROL, "test_rounding")
        result = pipeline.run(mock_container, {})

        expected = create_timeframe(expected)
        assert_frame_equal(result.df["time", "value"], expected.df["time", "value"])

    @pytest.mark.parametrize("decimals", [-1, 0.5, -1.5])
    def test_apply_rounding_invalid(self, mock_container: MagicMock, decimals: int) -> None:
        """Test that updated TimeFrame is returned."""
        tf = create_timeframe([1.234, 2.345, 3.456])

        config = MagicMock(spec=DataProcessingMethodConfig)
        config.method = "test_method"
        config.params = {"round": decimals}

        method_config = MagicMock(spec=DataProcessingConfig)
        method_config.method_configs = [config]

        mock_container.data = tf
        mock_container.qc_configs = [method_config]

        pipeline = MockOperationPipeline(OperationType.QUALITY_CONTROL, "test_rounding")
        with pytest.raises(
            (OverflowError, TypeError),
            match=(
                "out of range integral type conversion attempted|"
                "argument 'decimals': 'float' object cannot be interpreted as an integer"
            ),
        ):
            pipeline.run(mock_container, {})
