from datetime import datetime
from unittest.mock import MagicMock

import pytest

from dritimeseriesprocessor.models.domain_models.processing_config import (
    DataProcessingConfig,
    DataProcessingMethodConfig,
)
from dritimeseriesprocessor.operations.load.load_pipeline import LoadPipeline
from utils.data_creation import create_timeframe, make_time_series_container


def _make_config(method: str, params: dict) -> DataProcessingConfig:
    method_cfg = DataProcessingMethodConfig(method=method, params=params)
    cfg = MagicMock(spec=DataProcessingConfig)
    cfg.method_configs = [method_cfg]
    return cfg


class TestLoadApply:
    def test_load_copies_dep_data_into_container(self) -> None:
        """Tests that the load method copies the dependency's data column into the container."""
        container = make_time_series_container("target")
        container.source_column = "value"
        dep = make_time_series_container("dep")
        dep.data = create_timeframe([1.0, 2.0, 3.0])

        pipeline = LoadPipeline(
            data_router=MagicMock(), start_date=datetime(2024, 1, 1), end_date=datetime(2024, 1, 31)
        )
        result = pipeline.apply(
            container=container,
            config=DataProcessingMethodConfig(method="load", params={"dep_ts": "dep"}),
            dataset_repository={"dep": dep},
        )

        assert result.data is not None
        assert result.data.df["value"].to_list() == [1.0, 2.0, 3.0]

    def test_load_raises_when_dep_data_is_none(self) -> None:
        """Tests that load raises RuntimeError when the dependency has no data."""
        container = make_time_series_container("target")
        dep = make_time_series_container("dep")
        dep.data = None

        pipeline = LoadPipeline(
            data_router=MagicMock(), start_date=datetime(2024, 1, 1), end_date=datetime(2024, 1, 31)
        )
        with pytest.raises(RuntimeError, match="No data found for base dependency"):
            pipeline.apply(
                container=container,
                config=DataProcessingMethodConfig(method="load", params={"dep_ts": "dep"}),
                dataset_repository={"dep": dep},
            )

    def test_load_local_copy_stages_via_router_and_sets_staged_dir(self) -> None:
        """Tests that load-local-copy calls stage_locally and stores the result in staged_dir."""
        container = make_time_series_container("target")
        mock_router = MagicMock()
        staged = "/tmp/staged/raw"
        mock_router.stage_locally.return_value = staged

        start = datetime(2024, 1, 1)
        end = datetime(2024, 1, 31)

        pipeline = LoadPipeline(data_router=mock_router, start_date=start, end_date=end)
        result = pipeline.apply(
            container=container,
            config=DataProcessingMethodConfig(method="load-local-copy", params={}),
            dataset_repository={},
        )

        mock_router.stage_locally.assert_called_once_with(container, start, end)
        assert result.staged_dir == staged

    def test_apply_raises_for_unknown_method(self) -> None:
        """Tests that apply raises ValueError when the method is not recognised."""
        container = make_time_series_container("target")

        pipeline = LoadPipeline(
            data_router=MagicMock(), start_date=datetime(2024, 1, 1), end_date=datetime(2024, 1, 31)
        )
        with pytest.raises(ValueError, match="Unknown load method: not-a-method"):
            pipeline.apply(
                container=container,
                config=DataProcessingMethodConfig(method="not-a-method", params={}),
                dataset_repository={},
            )


class TestLoadRun:
    def test_run_iterates_all_method_configs(self) -> None:
        """Tests that run applies every method config in the DataProcessingConfig."""
        container = make_time_series_container("target")
        container.source_column = "value"
        dep = make_time_series_container("dep")
        dep.data = create_timeframe([5.0])

        dep2 = make_time_series_container("dep2")
        dep2.data = create_timeframe([9.0])

        method_cfg1 = DataProcessingMethodConfig(method="load", params={"dep_ts": "dep"})
        method_cfg2 = DataProcessingMethodConfig(method="load", params={"dep_ts": "dep2"})
        config = MagicMock(spec=DataProcessingConfig)
        config.method_configs = [method_cfg1, method_cfg2]

        pipeline = LoadPipeline(
            data_router=MagicMock(), start_date=datetime(2024, 1, 1), end_date=datetime(2024, 1, 31)
        )
        result = pipeline.run(container, {"dep": dep, "dep2": dep2}, config)

        # Second config overwrites first
        assert result.data is not None
        assert result.data.df["value"].to_list() == [9.0]
