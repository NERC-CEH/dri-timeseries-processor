from datetime import datetime
from unittest.mock import MagicMock

import polars as pl
import pytest
import time_stream as ts

from dritimeseriesprocessor.dag.dataset_dependency_graph import DatasetDependencyGraph
from dritimeseriesprocessor.io_backend.writer import ByteParquetWriter
from dritimeseriesprocessor.processing.time_series_processor import TimeSeriesProcessor
from dritimeseriesprocessor.utils.enums import OperationType
from utils.data_creation import make_time_series_container


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


@pytest.fixture
def mock_writer() -> MagicMock:
    """Create a mock ParquetWriterInterface for use in tests"""
    writer = MagicMock(spec=ByteParquetWriter)
    return writer


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
    def test_run_calls_process_datasets(
        self, topo_layers: list, mock_router: MagicMock, mock_writer: MagicMock
    ) -> None:
        """Test that the run method loops through all datasets in the graph and calls the process method on them"""
        mock_graph = create_mock_dag(topo_layers)

        processor = TimeSeriesProcessor(
            graph=mock_graph,
            data_router=mock_router,
            data_writer=mock_writer,
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 1, 3),
            metrics=MagicMock(),
        )
        # override the process dataset function for this test
        processor.process_dataset = MagicMock()
        processor._save_datasets = MagicMock()
        processor.run()
        assert processor.process_dataset.call_count == len(mock_graph.datasets)

    def test_load_raw(self, mock_router: MagicMock, mock_writer: MagicMock) -> None:
        ds_id = "ds1"
        mock_graph = create_mock_dag([[ds_id]])
        processor = TimeSeriesProcessor(
            graph=mock_graph,
            data_router=mock_router,
            data_writer=mock_writer,
            start_date=datetime(2023, 1, 1),
            end_date=datetime(2023, 1, 2),
            metrics=MagicMock(),
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

    def test_process(self, mock_router: MagicMock, mock_writer: MagicMock, monkeypatch: pytest.MonkeyPatch) -> None:
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
            "dritimeseriesprocessor.processing.time_series_processor.OPERATION_PIPELINES",
            {
                OperationType.CORRECTION: mock_corr_pipeline,
                OperationType.QUALITY_CONTROL: mock_qc_pipeline,
                OperationType.INFILLING: mock_infill_pipeline,
            },
        )

        processor = TimeSeriesProcessor(
            graph=mock_graph,
            data_router=mock_router,
            data_writer=mock_writer,
            start_date=datetime(2023, 1, 1),
            end_date=datetime(2023, 1, 2),
            metrics=MagicMock(),
        )

        raw_container = mock_graph.datasets[raw_ds_id]
        processor._load_raw(raw_container)
        processed_container = mock_graph.datasets[processed_ds_id]
        processed_container.all_dependencies = MagicMock(return_value=[raw_ds_id])
        processor._process(processed_container)

        mock_corr_pipeline.run.assert_called_once()
        mock_infill_pipeline.run.assert_called_once()
        mock_qc_pipeline.run.assert_called_once()
        assert raw_container.data == tf_result
        assert processed_container.data == tf_result

    def test_save_datasets(self, monkeypatch, processor):
        monkeypatch.setattr("your_module.ThreadPoolExecutor", ImmediateExecutor)
        monkeypatch.setattr("your_module.as_completed", lambda tasks: iter(tasks))

        # Make lots of (date, df) pairs
        fake_tf = MagicMock(df=object(), time_name="t")
        monkeypatch.setattr("your_module.merge_multiple_timeframes", lambda _: fake_tf)
        monkeypatch.setattr(
            "your_module.split_by_date",
            lambda *_: [(processor._dt("2026-02-10"), "df1"),
                        (processor._dt("2026-02-11"), "df2"),
                        (processor._dt("2026-02-12"), "df3")],
        )

        processor.data_writer.write = MagicMock()

        await_mock = MagicMock()
        monkeypatch.setattr("your_module.await_submission_slot", await_mock)

        processor._save_datasets(max_workers=2, max_submitted=2)

        assert await_mock.call_count >= 1