from datetime import datetime
from unittest.mock import MagicMock

import polars as pl
import pytest
import time_stream as ts

from new_processor.dag.dataset_dependency_graph import DatasetDependencyGraph
from new_processor.models.domain_models.method_config import MethodConfig
from new_processor.models.domain_models.time_series_container import TimeSeriesContainer
from new_processor.processing.time_series_processor import TimeSeriesProcessor
from new_processor.utils.enums import MethodType, OperationType, ProcessingLevel


def make_time_series_container(ts_id: str) -> TimeSeriesContainer:
    """Create a lightweight fake TimeSeriesContainer for use in tests.

    Args:
        ts_id: The time series ID.

    Returns:
        A TimeSeriesContainer instance
    """
    return TimeSeriesContainer(
        ts_id=ts_id,
        ref_id=ts_id + "_ref",
        network="network",
        source_bucket=ts_id + "_bucket",
        source_site=ts_id + "_site",
        source_column=ts_id + "_column",
        source_dataset=ts_id + "_dataset",
        resolution="P1D",
        periodicity="P1D",
        variable=ts_id + "_variable",
        processing_level=ProcessingLevel.PROCESSED,
        depends_on=[],
        qc_configs=set(),
        infill_configs=set(),
        correction_configs=set(),
        method=MethodConfig(method_type=MethodType.LOAD),
    )


@pytest.fixture
def mock_router() -> MagicMock:
    """Create a mock data_router for use in tests"""
    router = MagicMock()
    router.query_by_date_range.return_value = pl.DataFrame(
        {
            "time": [datetime(2025, 1, 1), datetime(2025, 1, 2), datetime(2025, 1, 3)],
            "value": [10, 20, 30],
        }
    )
    return router


def create_mock_dag(topo_layers: list) -> MagicMock:
    """Create a mock DAG for use in tests"""
    graph = MagicMock(spec=DatasetDependencyGraph)
    datasets_dict = {ds_id: make_time_series_container(ds_id) for layer in topo_layers for ds_id in layer}
    graph.layered_topo_sort.return_value = topo_layers
    graph.datasets = datasets_dict
    return graph


class TestTimeSeriesProcessor:
    @pytest.mark.parametrize(
        "topo_layers",
        [
            pytest.param([["ds1"]], id="single dataset"),
            pytest.param([["ds1"], ["ds2"]], id="single dataset in multiple layers"),
            pytest.param([["ds1", "ds2"]], id="multiple dataset in same layer"),
            pytest.param([["ds1", "ds2"], ["ds3", "ds4"]], id="multiple dataset in multiple layers"),
        ],
    )
    def test_run_calls_process_datasets(self, topo_layers: list, mock_router: MagicMock) -> None:
        """Test that the run method loops through all datasets in the graph and calls the process method on them"""
        mock_graph = create_mock_dag(topo_layers)

        processor = TimeSeriesProcessor(
            graph=mock_graph,
            data_router=mock_router,
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 1, 3),
        )
        # override the process dataset function for this test
        processor.process_dataset = MagicMock()
        processor.run()
        assert processor.process_dataset.call_count == len(mock_graph.datasets)

    def test_load_raw(self, mock_router: MagicMock) -> None:
        ds_id = "ds1"
        mock_graph = create_mock_dag([[ds_id]])
        processor = TimeSeriesProcessor(
            graph=mock_graph,
            data_router=mock_router,
            start_date=datetime(2023, 1, 1),
            end_date=datetime(2023, 1, 2),
        )

        container = mock_graph.datasets[ds_id]
        processor._load_raw(container)

        mock_router.query_by_date_range.assert_called_once()
        assert isinstance(container.data, ts.TimeFrame)

        # Metadata should be set
        expected_metadata = {"column_name": "ds1_column"}
        assert container.data.metadata == expected_metadata

        # Core flags should have been added
        assert "core_flags" in container.data.flag_systems
        assert "value_CORE_FLAG" in container.data.flag_columns

    def test_process(self, mock_router: MagicMock, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that _process runs all three pipelines in order and updates container.data"""
        raw_ds_id = "raw_ds1"
        processed_ds_id = "processed_ds1"

        mock_graph = create_mock_dag([[raw_ds_id], [processed_ds_id]])

        tf_result = MagicMock(spec=ts.TimeFrame)

        mock_corr_pipeline = MagicMock()
        mock_corr_pipeline.run.return_value = tf_result

        mock_infill_pipeline = MagicMock()
        mock_infill_pipeline.run.return_value = tf_result

        mock_qc_pipeline = MagicMock()
        mock_qc_pipeline.run.return_value = tf_result

        monkeypatch.setattr(
            "new_processor.processing.time_series_processor.OPERATION_PIPELINES",
            {
                OperationType.CORRECTION: mock_corr_pipeline,
                OperationType.QUALITY_CONTROL: mock_qc_pipeline,
                OperationType.INFILLING: mock_infill_pipeline,
            },
        )

        processor = TimeSeriesProcessor(
            graph=mock_graph,
            data_router=mock_router,
            start_date=datetime(2023, 1, 1),
            end_date=datetime(2023, 1, 2),
        )

        raw_container = mock_graph.datasets[raw_ds_id]
        processor._load_raw(raw_container)
        processed_container = mock_graph.datasets[processed_ds_id]
        processed_container.direct_depends_on = [raw_ds_id]

        processor._process(processed_container)

        mock_corr_pipeline.run.assert_called_once()
        mock_infill_pipeline.run.assert_called_once()
        mock_qc_pipeline.run.assert_called_once()
        assert raw_container.data == tf_result
        assert processed_container.data == tf_result
