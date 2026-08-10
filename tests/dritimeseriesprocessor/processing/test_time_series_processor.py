from datetime import datetime, timedelta
from unittest.mock import MagicMock

import polars as pl
import pytest
import time_stream as ts
from polars.testing import assert_frame_equal

from dritimeseriesprocessor.dag.dataset_dependency_graph import DatasetDependencyGraph
from dritimeseriesprocessor.io_backend.writer import ByteParquetWriter
from dritimeseriesprocessor.models.domain_models.processing_config import DataProcessingConfig
from dritimeseriesprocessor.processing.time_series_processor import TimeSeriesProcessor
from dritimeseriesprocessor.utils.enums import ConfigurationType, ProcessingLevel
from utils.data_creation import create_timeframe, dataframe_to_timeframe, make_time_series_container


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
    graph.flagging_systems = {}
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
        processor._batch_load = MagicMock()
        processor._save_datasets = MagicMock()
        processor.run()
        assert processor.process_dataset.call_count == len(mock_graph.datasets)

    def test_run_raises_when_a_dataset_is_marked_failed(self, mock_router: MagicMock, mock_writer: MagicMock) -> None:
        """Test that run raises an exception if any dataset ends up marked as failed, even if no exception
        propagated out of process_layer (e.g. because the failure happened during _batch_load).
        """
        mock_graph = create_mock_dag([["ds1"]])
        mock_graph.datasets["ds1"].failed = True

        processor = TimeSeriesProcessor(
            graph=mock_graph,
            data_router=mock_router,
            data_writer=mock_writer,
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 1, 3),
            metrics=MagicMock(),
        )
        processor.process_dataset = MagicMock()
        processor._batch_load = MagicMock()
        processor._save_datasets = MagicMock()

        with pytest.raises(RuntimeError, match="Processing failed for 1 dataset"):
            processor.run()

    def test_run_does_not_raise_when_no_datasets_failed(self, mock_router: MagicMock, mock_writer: MagicMock) -> None:
        """Test that run completes without raising when no dataset is marked as failed."""
        mock_graph = create_mock_dag([["ds1"]])

        processor = TimeSeriesProcessor(
            graph=mock_graph,
            data_router=mock_router,
            data_writer=mock_writer,
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 1, 3),
            metrics=MagicMock(),
        )
        processor.process_dataset = MagicMock()
        processor._batch_load = MagicMock()
        processor._save_datasets = MagicMock()

        processor.run()

    def test_process_layer_skips_load_only_containers(self, mock_router: MagicMock, mock_writer: MagicMock) -> None:
        """Load-only containers should not be passed to process_dataset."""
        mock_graph = create_mock_dag([["ds1", "ds2"]])
        mock_graph.datasets["ds2"].load_only = True

        processor = TimeSeriesProcessor(
            graph=mock_graph,
            data_router=mock_router,
            data_writer=mock_writer,
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 1, 3),
            metrics=MagicMock(),
        )
        processor.process_dataset = MagicMock()
        processor.process_layer(["ds1", "ds2"])

        processor.process_dataset.assert_called_once_with("ds1")

    def test_load_raw(self, mock_router: MagicMock, mock_writer: MagicMock) -> None:
        """Test that _batch_load reads a load container's data into a TimeFrame."""
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
        container.source_column = "value"  # Need to set this as the generic name of the mock dataframe
        processor._batch_load()

        mock_router.query_by_date_range.assert_called_once()
        assert isinstance(container.data, ts.TimeFrame)

        # Metadata should be set
        expected_metadata = {"column_name": "value"}
        assert container.data.metadata == expected_metadata

    def test_batch_load_reads_wider_than_the_requested_window(
        self, mock_router: MagicMock, mock_writer: MagicMock
    ) -> None:
        """Tests that the load window is widened so aggregation buckets at each edge get their full source data.

        A bucket labelled T covers (T - period, T] for a preceding time anchor and [T, T + period) for a following
        one, so source data is needed on both sides of the requested window.
        """
        ds_id = "ds1"
        mock_graph = create_mock_dag([[ds_id]])
        processor = TimeSeriesProcessor(
            graph=mock_graph,
            data_router=mock_router,
            data_writer=mock_writer,
            start_date=datetime(2025, 1, 10),
            end_date=datetime(2025, 1, 12),
            metrics=MagicMock(),
        )

        mock_graph.datasets[ds_id].source_column = "value"
        processor._batch_load()

        call_kwargs = mock_router.query_by_date_range.call_args.kwargs
        assert call_kwargs["start_date"] == datetime(2025, 1, 9)
        assert call_kwargs["end_date"] == datetime(2025, 1, 13)

    def test_build_save_tasks_drops_rows_outside_the_requested_window(
        self, mock_router: MagicMock, mock_writer: MagicMock
    ) -> None:
        """Tests that rows read only to complete edge buckets are not written out as their own day partitions."""
        ds_id = "ds1"
        mock_graph = create_mock_dag([[ds_id]])
        container = mock_graph.datasets[ds_id]
        container.processing_level = ProcessingLevel.PROCESSED
        container.network = "my_network"
        container.source_site_identifier = "SITE_A"
        container.resolution = "PT30M"
        container.source_bucket = "my_bucket"
        container.source_dataset = "my_dataset"
        container.source_column = "value"

        # Half-hourly data covering a day either side of the requested window
        times = [datetime(2025, 1, 1) + timedelta(minutes=30 * step) for step in range(192)]
        df = pl.DataFrame({"time": times, "value": [float(step) for step in range(192)]})
        container.data = dataframe_to_timeframe(df, resolution="PT30M", metadata={"column_name": "value"})

        processor = TimeSeriesProcessor(
            graph=mock_graph,
            data_router=mock_router,
            data_writer=mock_writer,
            start_date=datetime(2025, 1, 2),
            end_date=datetime(2025, 1, 3),
            metrics=MagicMock(),
        )

        written_dates = [key.split("date=")[1].split("/")[0] for _, key, _, _ in processor._build_save_tasks()]
        assert written_dates == ["2025-01-02", "2025-01-03"]

    def test_processing_failure_of_dependency(self, mock_router: MagicMock, mock_writer: MagicMock) -> None:
        """Test that failed tag is set to True when dataset fails processing.
        The failure can happen at any of LOAD, PROCESS, AGGREGATE and DERIVE stages.
        """
        topo_layers = [["ds1", "ds2"], ["ds3", "ds4"]]
        mock_graph = create_mock_dag(topo_layers)

        ds1 = mock_graph.datasets["ds1"]
        ds2 = mock_graph.datasets["ds2"]
        ds3 = mock_graph.datasets["ds3"]
        ds4 = mock_graph.datasets["ds4"]

        ds3.all_dependencies = MagicMock(return_value=["ds1", "ds2"])
        ds4.all_dependencies = MagicMock(return_value=["ds1"])

        # Attach configs so ds3/ds4 are not treated as load-only and reach the dependency-failure check.
        # plan_order has an entry but the dependency check returns before any pipeline actually runs.
        ds3.data_processing_configs = {"cfg": MagicMock()}
        ds3.plan_order = ["cfg"]
        ds4.data_processing_configs = {"cfg": MagicMock()}
        ds4.plan_order = ["cfg"]

        processor = TimeSeriesProcessor(
            graph=mock_graph,
            data_router=mock_router,
            data_writer=mock_writer,
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 1, 2),
            metrics=MagicMock(),
        )

        real_process_dataset = processor.process_dataset

        def fail_inside_process_dataset(dataset_id: str) -> None:
            if dataset_id == "ds2":
                raise Exception("boom during process_dataset")
            return real_process_dataset(dataset_id)

        processor._batch_load = MagicMock()
        processor.process_dataset = MagicMock(side_effect=fail_inside_process_dataset)
        processor._save_datasets = MagicMock()
        with pytest.raises(RuntimeError, match="Processing failed for"):
            processor.run()

        # ds1 should not be marked as failed
        assert not ds1.failed

        # ds2 raised an exception, so it should be marked as failed
        assert ds2.failed
        # Only ds2 should have triggered the metrics failure counter, labelled with its dataset id
        processor.metrics.failed.labels.assert_called_once_with(dataset="ds2")  # type: ignore[union-attr]
        assert processor.metrics.failed.labels.return_value.inc.call_count == 1  # type: ignore[union-attr]

        # ds3 depends on ds2, so it should be marked as failed too
        assert ds3.failed

        # ds4 depends only on ds1, so it should not be marked as failed
        assert not ds4.failed

    def test_batch_load_marks_all_containers_failed_on_query_error(
        self, mock_router: MagicMock, mock_writer: MagicMock
    ) -> None:
        """When the data router raises, all containers in the group should be marked as failed."""
        mock_graph = create_mock_dag([["ds1", "ds2"]])
        mock_router.query_by_date_range.side_effect = RuntimeError("connection failed")

        processor = TimeSeriesProcessor(
            graph=mock_graph,
            data_router=mock_router,
            data_writer=mock_writer,
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 1, 2),
            metrics=MagicMock(),
        )

        ds1 = mock_graph.datasets["ds1"]
        ds2 = mock_graph.datasets["ds2"]
        ds1.source_column = "value"
        ds2.source_column = "value"

        processor._batch_load()

        assert ds1.failed
        assert ds2.failed
        assert ds1.data is None
        assert ds2.data is None

    def test_batch_load_marks_all_containers_failed_on_empty_result(
        self, mock_router: MagicMock, mock_writer: MagicMock
    ) -> None:
        """When the data router returns an empty DataFrame, all containers in the group should be marked as failed."""
        mock_graph = create_mock_dag([["ds1", "ds2"]])
        mock_router.query_by_date_range.return_value = pl.DataFrame()

        processor = TimeSeriesProcessor(
            graph=mock_graph,
            data_router=mock_router,
            data_writer=mock_writer,
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 1, 2),
            metrics=MagicMock(),
        )

        ds1 = mock_graph.datasets["ds1"]
        ds2 = mock_graph.datasets["ds2"]
        ds1.source_column = "value"
        ds2.source_column = "value"

        processor._batch_load()

        assert ds1.failed
        assert ds2.failed

    def test_batch_load_marks_single_container_failed_on_missing_column(
        self, mock_router: MagicMock, mock_writer: MagicMock
    ) -> None:
        """When a container's column is missing from the result, only that container should be marked as failed."""
        mock_graph = create_mock_dag([["ds1", "ds2"]])
        # The returned DataFrame has "value" but not "missing_col"
        mock_router.query_by_date_range.return_value = pl.DataFrame(
            {
                "time": [datetime(2025, 1, 1), datetime(2025, 1, 2)],
                "value": [10, 20],
            }
        )

        processor = TimeSeriesProcessor(
            graph=mock_graph,
            data_router=mock_router,
            data_writer=mock_writer,
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 1, 2),
            metrics=MagicMock(),
        )

        ds1 = mock_graph.datasets["ds1"]
        ds2 = mock_graph.datasets["ds2"]
        ds1.source_column = "value"
        ds2.source_column = "missing_col"

        processor._batch_load()

        assert not ds1.failed
        assert ds1.data is not None
        assert ds2.failed
        assert ds2.data is None

    def test_collect_load_containers_skips_processed_dataset_with_no_configs(
        self, mock_router: MagicMock, mock_writer: MagicMock
    ) -> None:
        """Tests that a processed dataset with no processing configs is marked as failed and not loaded."""
        mock_graph = create_mock_dag([["ds1"]])
        container = mock_graph.datasets["ds1"]
        container.processing_level = ProcessingLevel.PROCESSED

        processor = TimeSeriesProcessor(
            graph=mock_graph,
            data_router=mock_router,
            data_writer=mock_writer,
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 1, 2),
            metrics=MagicMock(),
        )

        assert processor._collect_load_containers() == []
        assert container.failed
        processor.metrics.no_data.labels.assert_called_once_with(dataset=container.ts_id)  # type: ignore[union-attr]
        assert processor.metrics.no_data.labels.return_value.inc.call_count == 1  # type: ignore[union-attr]

    def test_collect_load_containers_keeps_load_only_processed_dataset(
        self, mock_router: MagicMock, mock_writer: MagicMock
    ) -> None:
        """Tests that a load-only processed dataset is still loaded, since it is read from the processed store."""
        mock_graph = create_mock_dag([["ds1"]])
        container = mock_graph.datasets["ds1"]
        container.processing_level = ProcessingLevel.PROCESSED
        container.load_only = True

        processor = TimeSeriesProcessor(
            graph=mock_graph,
            data_router=mock_router,
            data_writer=mock_writer,
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 1, 2),
            metrics=MagicMock(),
        )

        assert processor._collect_load_containers() == [container]
        assert not container.failed

    def test_batch_load_does_not_query_for_processed_dataset_with_no_configs(
        self, mock_router: MagicMock, mock_writer: MagicMock
    ) -> None:
        """Tests that a processed dataset with no configs is failed without the data router being queried."""
        mock_graph = create_mock_dag([["ds1"]])
        container = mock_graph.datasets["ds1"]
        container.processing_level = ProcessingLevel.PROCESSED

        processor = TimeSeriesProcessor(
            graph=mock_graph,
            data_router=mock_router,
            data_writer=mock_writer,
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 1, 2),
            metrics=MagicMock(),
        )

        processor._batch_load()

        mock_router.query_by_date_range.assert_not_called()
        assert container.failed
        assert container.data is None

    def test_build_save_tasks_excludes_load_only_containers(
        self, mock_router: MagicMock, mock_writer: MagicMock
    ) -> None:
        """Load-only containers must not appear in save tasks even when processing_level is PROCESSED."""
        ds_ids = ["ds1", "ds2"]
        mock_graph = create_mock_dag([[ds_id] for ds_id in ds_ids])

        for ds_id, container in mock_graph.datasets.items():
            container.processing_level = ProcessingLevel.PROCESSED
            container.network = "my_network"
            container.source_site_identifier = "SITE_A"
            container.resolution = "PT30M"
            container.source_bucket = "my_bucket"
            container.data = create_timeframe(values=[i for i in range(48)], column_name=f"{ds_id}-col")

        mock_graph.datasets["ds2"].load_only = True

        processor = TimeSeriesProcessor(
            graph=mock_graph,
            data_router=mock_router,
            data_writer=mock_writer,
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 1, 2),
            metrics=MagicMock(),
        )

        tasks = list(processor._build_save_tasks())

        assert len(tasks) == 2
        for _, _, df, _ in tasks:
            assert "ds1-col" in df.columns
            assert "ds2-col" not in df.columns

    def test_build_save_tasks_excludes_failed_containers(self, mock_router: MagicMock, mock_writer: MagicMock) -> None:
        """Failed containers should be excluded from save tasks."""
        ds_ids = ["ds1", "ds2"]
        mock_graph = create_mock_dag([[ds_id] for ds_id in ds_ids])

        for ds_id, container in mock_graph.datasets.items():
            container.processing_level = ProcessingLevel.PROCESSED
            container.network = "my_network"
            container.source_site_identifier = "SITE_A"
            container.resolution = "PT30M"
            container.source_bucket = "my_bucket"
            container.data = create_timeframe(values=[i for i in range(48)], column_name=f"{ds_id}-col")

        # Mark ds2 as failed
        mock_graph.datasets["ds2"].failed = True

        processor = TimeSeriesProcessor(
            graph=mock_graph,
            data_router=mock_router,
            data_writer=mock_writer,
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 1, 2),
            metrics=MagicMock(),
        )

        tasks = list(processor._build_save_tasks())

        # Only ds1 data should be present - 2 tasks for 2 days
        assert len(tasks) == 2
        for _, _, df, _ in tasks:
            assert "ds1-col" in df.columns
            assert "ds2-col" not in df.columns

    def test_process_dataset_raises_when_plan_order_empty(self, mock_router: MagicMock, mock_writer: MagicMock) -> None:
        """Tests that process_dataset raises if a container has processing configs but no plan_order - this
        happens if the metadata service returns a dataset's processing configs but no methodology steps.
        """
        mock_graph = create_mock_dag([["ds1"]])
        container = mock_graph.datasets["ds1"]
        container.data_processing_configs = {"cfg": MagicMock(spec=DataProcessingConfig)}
        container.plan_order = []

        processor = TimeSeriesProcessor(
            graph=mock_graph,
            data_router=mock_router,
            data_writer=mock_writer,
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 1, 2),
            metrics=MagicMock(),
        )

        with pytest.raises(RuntimeError, match="no plan"):
            processor.process_dataset("ds1")

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
            container.source_dataset = "my_dataset"
            container.source_column = f"{ds_id}-col"
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


class TestProcessDatasetQCRemoval:
    def test_remove_flagged_requested_for_single_qc_block(
        self, mock_router: MagicMock, mock_writer: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Tests that the single QC step is run with remove_flagged=True so flagged data is removed."""
        mock_graph = create_mock_dag([["ds1"]])
        container = mock_graph.datasets["ds1"]

        qc_cfg = MagicMock(spec=DataProcessingConfig)
        qc_cfg.config_type = ConfigurationType.QUALITY_CONTROL
        qc_cfg.method_configs = []
        container.data_processing_configs = {"qc": qc_cfg}
        container.plan_order = ["qc"]
        container.data = create_timeframe([1.0, 2.0])

        remove_flagged_calls: list[bool] = []
        monkeypatch.setattr(
            "dritimeseriesprocessor.processing.time_series_processor.QCPipeline.run",
            lambda self, container, repo, config, *, remove_flagged=True: (
                remove_flagged_calls.append(remove_flagged),
                container.data,
            )[1],
        )

        processor = TimeSeriesProcessor(
            graph=mock_graph,
            data_router=mock_router,
            data_writer=mock_writer,
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 1, 2),
            metrics=MagicMock(),
        )
        processor.process_dataset("ds1")

        assert remove_flagged_calls == [True]

    def test_remove_flagged_requested_only_after_final_qc_step(
        self, mock_router: MagicMock, mock_writer: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Tests that only the final QC step in a sequential pair is run with remove_flagged=True."""
        mock_graph = create_mock_dag([["ds1"]])
        container = mock_graph.datasets["ds1"]

        def _qc_cfg() -> MagicMock:
            cfg = MagicMock(spec=DataProcessingConfig)
            cfg.config_type = ConfigurationType.QUALITY_CONTROL
            cfg.method_configs = []
            return cfg

        container.data_processing_configs = {"qc1": _qc_cfg(), "qc2": _qc_cfg()}
        container.plan_order = ["qc1", "qc2"]
        container.data = create_timeframe([1.0, 2.0])

        remove_flagged_calls: list[bool] = []
        monkeypatch.setattr(
            "dritimeseriesprocessor.processing.time_series_processor.QCPipeline.run",
            lambda self, container, repo, config, *, remove_flagged=True: (
                remove_flagged_calls.append(remove_flagged),
                container.data,
            )[1],
        )

        processor = TimeSeriesProcessor(
            graph=mock_graph,
            data_router=mock_router,
            data_writer=mock_writer,
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 1, 2),
            metrics=MagicMock(),
        )
        processor.process_dataset("ds1")

        # qc1 runs without removal (a later QC step follows); qc2 runs with removal (it is the final QC step).
        assert remove_flagged_calls == [False, True]


class TestGetNextStepType:
    def _make_processor(self, mock_router: MagicMock, mock_writer: MagicMock) -> TimeSeriesProcessor:
        mock_graph = create_mock_dag([["ds1"]])
        return TimeSeriesProcessor(
            graph=mock_graph,
            data_router=mock_router,
            data_writer=mock_writer,
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 1, 2),
            metrics=MagicMock(),
        )

    def test_returns_config_type_of_next_step(self, mock_router: MagicMock, mock_writer: MagicMock) -> None:
        """Tests that the config type of the step after current_idx is returned."""
        container = make_time_series_container("ds1")
        container.plan_order = ["step_a", "step_b"]

        cfg_a = MagicMock(spec=DataProcessingConfig)
        cfg_a.config_type = ConfigurationType.QUALITY_CONTROL
        cfg_b = MagicMock(spec=DataProcessingConfig)
        cfg_b.config_type = ConfigurationType.INFILLING

        container.data_processing_configs = {"step_a": cfg_a, "step_b": cfg_b}

        result = TimeSeriesProcessor._get_next_step_type(container, 0)

        assert result == ConfigurationType.INFILLING

    def test_returns_none_when_current_step_is_last(self, mock_router: MagicMock, mock_writer: MagicMock) -> None:
        """Tests that None is returned when there is no step after current_idx."""
        container = make_time_series_container("ds1")
        container.plan_order = ["step_a"]

        cfg_a = MagicMock(spec=DataProcessingConfig)
        cfg_a.config_type = ConfigurationType.QUALITY_CONTROL
        container.data_processing_configs = {"step_a": cfg_a}

        result = TimeSeriesProcessor._get_next_step_type(container, 0)

        assert result is None
