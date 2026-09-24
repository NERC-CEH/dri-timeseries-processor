from typing import Any
from unittest.mock import MagicMock

import pytest
import time_stream as ts
from polars.testing import assert_frame_equal
from tests.utils.data_creation import create_timeframe

from dritimeseriesprocessor.models.domain_models.processing_config import (
    DataProcessingConfig,
    DataProcessingMethodConfig,
)
from dritimeseriesprocessor.models.domain_models.time_series_container import TimeSeriesContainer
from dritimeseriesprocessor.operations.operation_pipeline import OperationPipeline
from dritimeseriesprocessor.utils.enums import ConfigurationType, ProcessingLevel


class MockOperationPipeline(OperationPipeline):
    """Implementation of OperationPipeline for testing."""

    def apply(self, tf: ts.TimeFrame, *_, **__) -> ts.TimeFrame:
        return tf

    def get_flag_column(self, column: str) -> str:
        return f"{column}_TEST_FLAG"

    def compute_flag_mask(self, tf: ts.TimeFrame, result: Any, column_name: str) -> MagicMock:
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
    container.flag_column_schemes = {}
    return container


@pytest.fixture
def proc_config() -> MagicMock:
    """Create a mock DataProcessingConfig with a single method config."""
    method_config = MagicMock(spec=DataProcessingMethodConfig)
    method_config.method = "test_method"
    method_config.params = {}

    config = MagicMock(spec=DataProcessingConfig)
    config.method_configs = [method_config]
    return config


class TestInitFlagColumns:
    def test_creates_core_and_operation_flag_columns(self, mock_timeframe: MagicMock) -> None:
        """Tests that the core and operation-specific flag columns are set up for each data column."""
        pipeline = MockOperationPipeline(
            ConfigurationType.QUALITY_CONTROL,
            {"core_flags": {"unchecked": 32}, "test_flags": {"flag1": 1}},
        )
        mock_timeframe.flag_systems = {}
        flag_column_schemes = {"value_CORE_FLAG": "core_flags", "value_TEST_FLAG": "test_flags"}

        pipeline._init_flag_columns(mock_timeframe, flag_column_schemes)

        mock_timeframe.init_flag_column.assert_any_call("core_flags", "value_CORE_FLAG")
        mock_timeframe.init_flag_column.assert_any_call("test_flags", "value_TEST_FLAG")

    def test_skips_columns_not_in_schemes(self, mock_timeframe: MagicMock) -> None:
        """Tests that flag columns the dataset does not define are not created."""
        pipeline = MockOperationPipeline(ConfigurationType.QUALITY_CONTROL, {})
        mock_timeframe.flag_systems = {}

        pipeline._init_flag_columns(mock_timeframe, {})

        mock_timeframe.init_flag_column.assert_not_called()


class TestRun:
    def test_returns_updated_timeframe(
        self, mock_container: MagicMock, mock_timeframe: MagicMock, proc_config: MagicMock
    ) -> None:
        """Test that updated TimeFrame is returned."""
        pipeline = MockOperationPipeline(ConfigurationType.QUALITY_CONTROL, {})
        updated_tf = MagicMock()
        pipeline.core_flag_updater = MagicMock(return_value=updated_tf)

        result = pipeline.run(mock_container, {}, proc_config)
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

        pipeline = MockOperationPipeline(ConfigurationType.QUALITY_CONTROL, {})
        result = pipeline.run(mock_container, {}, method_config)

        expected_tf = create_timeframe(expected)
        assert_frame_equal(result.df["time", "value"], expected_tf.df["time", "value"])

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

        pipeline = MockOperationPipeline(ConfigurationType.QUALITY_CONTROL, {})
        with pytest.raises((OverflowError, TypeError)):
            pipeline.run(mock_container, {}, method_config)


class TestInjectDependencyTimeframes:
    @staticmethod
    def dependency(source_column: str | None) -> TimeSeriesContainer:
        """Create a dependency container holding a TimeFrame of its own."""
        data = create_timeframe([1.0, 2.0], source_column) if source_column else None
        return TimeSeriesContainer(
            ts_id=f"ts-{source_column}",
            network="cosmos",
            source_bucket=None,
            source_dataset=None,
            source_column=source_column,
            source_site=None,
            source_site_identifier=None,
            time_column_name="time",
            unit=None,
            resolution="PT1H",
            periodicity="PT1H",
            time_anchor="start",
            processing_level=ProcessingLevel.PROCESSED,
            data=data,
        )

    def test_single_dependency_id_is_injected_under_its_column_name(self) -> None:
        """Tests that a param holding one dataset id adds that dependency's data under its lowercased column."""
        config = DataProcessingMethodConfig(method="test", params={"dep_ts": "ts_1"})
        repository = {"ts_1": self.dependency("TA")}

        OperationPipeline._inject_dependency_timeframes(config, repository, ("dep_ts",))

        assert config.params["ta"] is repository["ts_1"].data

    def test_list_of_dependency_ids_is_injected(self) -> None:
        """Tests that a param holding several dataset ids adds every one of those dependencies."""
        config = DataProcessingMethodConfig(method="test", params={"dep_ts": ["ts_1", "ts_2"]})
        repository = {"ts_1": self.dependency("TA"), "ts_2": self.dependency("RH")}

        OperationPipeline._inject_dependency_timeframes(config, repository, ("dep_ts",))

        assert config.params["ta"] is repository["ts_1"].data
        assert config.params["rh"] is repository["ts_2"].data

    def test_dependencies_are_collected_from_every_given_key(self) -> None:
        """Tests that dependency ids are read from all of the param names the pipeline asks for."""
        config = DataProcessingMethodConfig(method="test", params={"dep_ts": "ts_1", "load_dep_ts": "ts_2"})
        repository = {"ts_1": self.dependency("TA"), "ts_2": self.dependency("RH")}

        OperationPipeline._inject_dependency_timeframes(config, repository, ("dep_ts", "load_dep_ts"))

        assert config.params["ta"] is repository["ts_1"].data
        assert config.params["rh"] is repository["ts_2"].data

    def test_dependency_without_a_source_column_is_skipped(self) -> None:
        """Tests that a dependency with no source column of its own is left out, as it cannot be keyed."""
        config = DataProcessingMethodConfig(method="test", params={"dep_ts": "ts_1"})
        repository = {"ts_1": self.dependency(None)}

        OperationPipeline._inject_dependency_timeframes(config, repository, ("dep_ts",))

        assert config.params == {"dep_ts": "ts_1"}

    @pytest.mark.parametrize("params", [{}, {"dep_ts": None}], ids=["key missing", "key empty"])
    def test_nothing_is_injected_when_there_are_no_dependency_ids(self, params: dict) -> None:
        """Tests that params are left alone when the dependency key is absent or holds nothing."""
        config = DataProcessingMethodConfig(method="test", params=dict(params))

        OperationPipeline._inject_dependency_timeframes(config, {}, ("dep_ts",))

        assert config.params == params
