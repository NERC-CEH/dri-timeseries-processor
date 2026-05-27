from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

import polars as pl
import pytest
import time_stream as ts
from polars.testing import assert_frame_equal

from dritimeseriesprocessor.dag.dataset_dependency_graph import DatasetDependencyGraph
from dritimeseriesprocessor.io_backend.writer import ByteParquetWriter
from dritimeseriesprocessor.models.domain_models.processing_config import DataProcessingConfig
from dritimeseriesprocessor.models.domain_models.site_metadata import SiteMetadata
from dritimeseriesprocessor.processing.time_series_processor import TimeSeriesProcessor
from dritimeseriesprocessor.utils.enums import ConfigurationType, MethodType, OperationType, ProcessingLevel
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
        processor._batch_load_raw = MagicMock()
        processor._save_datasets = MagicMock()
        processor.run()
        assert processor.process_dataset.call_count == len(mock_graph.datasets)

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
        processor._batch_load_raw(container)

        mock_router.query_by_date_range.assert_called_once()
        assert isinstance(container.data, ts.TimeFrame)

        # Metadata should be set
        expected_metadata = {"column_name": "value"}
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
        raw_container.source_column = "value"
        processor._batch_load_raw(raw_container)
        processed_container = mock_graph.datasets[processed_ds_id]
        processed_container.source_column = "value"
        processed_container.all_dependencies = MagicMock(return_value=[raw_ds_id])
        processed_container.method_config = DataProcessingConfig(
            ts_id=processed_ds_id,
            config_id="process_config",
            config_type=ConfigurationType.PROCESS,
            method_configs=[MagicMock(params={"dep_ts": raw_ds_id})],
        )
        processor._process(processed_container)

        mock_corr_pipeline.run.assert_called_once()
        mock_infill_pipeline.run.assert_called_once()
        mock_qc_pipeline.run.assert_called_once()
        assert processed_container.data == tf_result

    def test_load_local_copy_downloads_raw_files_using_container_site_fields(
        self, mock_router: MagicMock, mock_writer: MagicMock
    ) -> None:
        container = make_time_series_container("raw_flux")
        container.source_bucket = "raw-bucket"
        container.source_site = "flux-plynl"
        container.source_site_identifier = "PLYNL"
        container.source_dataset = "Flux"
        container.network = "fdri"

        mock_graph = create_mock_dag([["raw_flux"]])
        mock_graph.datasets["raw_flux"] = container

        flux_s3_client = MagicMock()
        processor = TimeSeriesProcessor(
            graph=mock_graph,
            data_router=mock_router,
            data_writer=mock_writer,
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 1, 2),
            metrics=MagicMock(),
            flux_s3_client=flux_s3_client,
        )

        processor._load_local_copy(container)

        assert container.ts_id in processor._raw_dirs
        local_dir = Path(processor._raw_dirs[container.ts_id].name)
        assert local_dir.name.startswith("eddypro_raw_PLYNL_")
        flux_s3_client.download_raw_dat_files.assert_called_once_with(
            bucket="raw-bucket",
            site="flux-plynl",
            dataset="Flux",
            network="fdri",
            start_date=datetime(2025, 1, 1).date(),
            end_date=datetime(2025, 1, 2).date(),
            local_dir=local_dir,
        )

    def test_run_eddypro_passes_raw_dependency_and_ancillary_containers(
        self, mock_router: MagicMock, mock_writer: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        raw_container = make_time_series_container("raw_flux")
        raw_container.method_type = MagicMock(return_value=MethodType.LOAD_LOCAL_COPY)
        raw_container.source_site = "flux-plynl"

        ancillary_container = make_time_series_container("ancillary")
        ancillary_container.method_type = MagicMock(return_value=MethodType.LOAD)

        eddypro_container = make_time_series_container("eddypro_output")
        eddypro_container.method_type = MagicMock(return_value=MethodType.EDDYPRO)
        eddypro_container.source_site = "flux-plynl"
        eddypro_container.network = "fdri"
        eddypro_container.source_bucket = "processed-bucket"
        eddypro_container.source_dataset = "eddypro-full-output"
        eddypro_container.method_config = DataProcessingConfig(
            ts_id="eddypro_output",
            config_id="config-1",
            config_type=ConfigurationType.EDDYPRO,
            method_configs=[],
        )
        eddypro_container.all_dependencies = MagicMock(return_value=["raw_flux", "ancillary"])

        mock_graph = create_mock_dag([["raw_flux", "ancillary"], ["eddypro_output"]])
        mock_graph.datasets = {
            "raw_flux": raw_container,
            "ancillary": ancillary_container,
            "eddypro_output": eddypro_container,
        }
        mock_graph.site_metadata = {
            "http://fdri.ceh.ac.uk/id/site/flux-plynl": SiteMetadata(
                site_id="http://fdri.ceh.ac.uk/id/site/flux-plynl",
                network="fdri",
                alt_id="PLYNL",
            )
        }

        pipeline_run = MagicMock()
        pipeline_instance = MagicMock()
        pipeline_instance.run = pipeline_run

        monkeypatch.setattr(
            "dritimeseriesprocessor.processing.time_series_processor.EddyProPipeline",
            MagicMock(return_value=pipeline_instance),
        )
        monkeypatch.setattr(
            "dritimeseriesprocessor.processing.time_series_processor.EddyProRunner",
            MagicMock(return_value=MagicMock()),
        )

        flux_s3_client = MagicMock()
        processor = TimeSeriesProcessor(
            graph=mock_graph,
            data_router=mock_router,
            data_writer=mock_writer,
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 1, 2),
            metrics=MagicMock(),
            flux_s3_client=flux_s3_client,
        )
        processor._raw_dirs[raw_container.ts_id] = MagicMock(name="/tmp/staged_raw_dir")
        processor._raw_dirs[raw_container.ts_id].name = "/tmp/staged_raw_dir"

        processor._run_eddypro(eddypro_container)

        pipeline_run.assert_called_once_with(
            raw_data_dir=Path("/tmp/staged_raw_dir"),
            method_config=eddypro_container.method_config,
            site_metadata=mock_graph.site_metadata["http://fdri.ceh.ac.uk/id/site/flux-plynl"],
            start_date=datetime(2025, 1, 1).date(),
            end_date=datetime(2025, 1, 2).date(),
            ancillary_containers=[ancillary_container],
        )

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

        processor._batch_load_raw = MagicMock()
        processor.process_dataset = MagicMock(side_effect=fail_inside_process_dataset)
        processor._save_datasets = MagicMock()
        processor.run()

        # ds1 should not be marked as failed
        assert not ds1.failed

        # ds2 raised an exception, so it should be marked as failed
        assert ds2.failed
        # Only ds2 should have triggered the metrics failure counter
        assert processor.metrics.failed.inc.call_count == 1  # type: ignore[union-attr]

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

        processor._batch_load_raw(ds1, ds2)

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

        processor._batch_load_raw(ds1, ds2)

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

        processor._batch_load_raw(ds1, ds2)

        assert not ds1.failed
        assert ds1.data is not None
        assert ds2.failed
        assert ds2.data is None

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
