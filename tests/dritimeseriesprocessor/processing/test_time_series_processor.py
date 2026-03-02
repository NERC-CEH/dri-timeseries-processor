from datetime import datetime
from unittest.mock import MagicMock

import polars as pl
import pytest
import time_stream as ts
from polars.testing import assert_frame_equal

from dritimeseriesprocessor.dag.dataset_dependency_graph import DatasetDependencyGraph
from dritimeseriesprocessor.io_backend.writer import ByteParquetWriter
from dritimeseriesprocessor.processing.time_series_processor import TimeSeriesProcessor
from dritimeseriesprocessor.utils.enums import OperationType, ProcessingLevel
from utils.data_creation import create_timeframe, make_time_series_container


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

    def test_dependency_processing_failure(mock_router: MagicMock, mock_writer: MagicMock) -> None:
        """
        Test that process tag is dynamically added to dataset and set to false when dataset fails processing.
        The failure can happen at any of LOAD, PROCESS, AGGREGATE and DERIVE stages.
        Test that process tag is dynamically added to dataset, set to false if any dataset dependency fails processing.
        """
        topo_layers = [["ds1", "ds2"], ["ds3"]]
        mock_graph = create_mock_dag(topo_layers)
        ds1 = mock_graph.datasets["ds1"]
        ds2 = mock_graph.datasets["ds2"]
        ds3 = mock_graph.datasets["ds3"]
        ds3.all_dependencies = MagicMock(return_value=["ds1", "ds2"])

        processor = TimeSeriesProcessor(
            graph=mock_graph,
            data_router=mock_router,
            data_writer=mock_writer,
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 1, 3),
            metrics=MagicMock(),
        )

        real_process_dataset = processor.process_dataset

        def fail_inside_process_dataset(dataset_id: str) -> None:
            if dataset_id == "ds2":
                raise Exception("boom during process_dataset")
            return real_process_dataset(dataset_id)

        processor._load_raw = MagicMock()
        processor.process_dataset = MagicMock(side_effect=fail_inside_process_dataset)
        processor._save_datasets = MagicMock()
        processor.run()

        assert not hasattr(ds1, "processed")
        assert hasattr(ds2, "processed")
        assert ds2.processed is False
        assert processor.metrics.failed.inc.call_count == 1
        assert hasattr(ds3, "processed")
        assert ds3.processed is False

    def test_build_save_tasks(
        self, mock_router: MagicMock, mock_writer: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ds_ids = ["ds1", "ds2", "ds3"]
        mock_graph = create_mock_dag([[ds_id] for ds_id in ds_ids])

        # ensure all the containers have the required attributes for saving / key building
        for ds_id, container in mock_graph.datasets.items():
            container.processing_level = ProcessingLevel.PROCESSED
            container.network = "my_network"
            container.source_site_identifier = "SITE_A"
            container.resolution = "PT30M"
            container.source_bucket = "my_bucket"
            container.data = create_timeframe(values=[i for i in range(48)], column_name=f"{ds_id}-col")

        processor = TimeSeriesProcessor(
            graph=mock_graph,
            data_router=mock_router,
            data_writer=mock_writer,
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 1, 2),
            metrics=MagicMock(),
        )

        # All ds_ids should be grouped together, so we should only have 2 save tasks for the 2 days of data
        expected_df = mock_graph.datasets["ds1"].data.df
        expected_df = expected_df.with_columns([pl.Series(f"{ds_id}-col", [i for i in range(48)]) for ds_id in ds_ids])

        expected = [
            (
                "my_bucket",
                "my_network/resolution=PT30M/site=SITE_A/date=2025-01-01/data.parquet",
                expected_df.filter(pl.col("time").cast(pl.Date) == pl.date(2025, 1, 1)),
                "time",
            ),
            (
                "my_bucket",
                "my_network/resolution=PT30M/site=SITE_A/date=2025-01-02/data.parquet",
                expected_df.filter(pl.col("time").cast(pl.Date) == pl.date(2025, 1, 2)),
                "time",
            ),
        ]

        for idx, result in enumerate(processor._build_save_tasks()):
            result_bucket, result_key, result_df, result_time_name = result
            expected_bucket, expected_key, expected_df, expected_time_name = expected[idx]

            assert result_bucket == expected_bucket
            assert result_key == expected_key
            assert_frame_equal(result_df, expected_df)
            assert result_time_name == expected_time_name
