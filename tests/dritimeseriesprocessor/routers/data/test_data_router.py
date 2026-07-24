from datetime import datetime
from pathlib import Path
from typing import Iterator
from unittest.mock import MagicMock

import polars as pl
import pytest
from polars.testing import assert_frame_equal
from tests.utils.metadata_helpers import E2E_INPUT_BUCKET
from tests.utils.s3_test_helpers import get_s3_storage_client

from dritimeseriesprocessor.io_backend.duckdb_connection import create_duckdb_factory
from dritimeseriesprocessor.io_backend.reader import DuckDBParquetReader, RawFileReader
from dritimeseriesprocessor.routers.data.data_router import S3DataRouter
from dritimeseriesprocessor.storage.storage_client import S3StorageClient
from dritimeseriesprocessor.utils.enums import ProcessingLevel

TEST_DF = pl.DataFrame({"time": [datetime(2023, 1, 1), datetime(2023, 1, 2)], "value": [10, 20]})


@pytest.fixture
def mock_reader() -> MagicMock:
    """Mock out DuckDBParquetReader so no backend is needed."""
    reader = MagicMock()
    reader.read.return_value = TEST_DF
    return reader


@pytest.fixture
def mock_raw_reader() -> MagicMock:
    return MagicMock(spec=RawFileReader)


@pytest.fixture
def router(mock_reader: MagicMock, mock_raw_reader: MagicMock) -> S3DataRouter:
    return S3DataRouter(mock_reader, mock_raw_reader)


@pytest.fixture(scope="module")
def s3_storage_client() -> Iterator[S3StorageClient]:
    with get_s3_storage_client() as storage_client:
        yield storage_client


class TestS3DataRouter:
    def test_query_by_date_range(self, router: S3DataRouter, mock_reader: MagicMock) -> None:
        start = datetime(2023, 1, 1)
        end = datetime(2023, 1, 2)

        container = MagicMock(
            source_bucket="a_bucket",
            source_dataset="a_data",
            network="a_network",
            source_site="a_network-a_site",
            source_column="a_column_name",
            source_site_identifier="A_SITE",
            resolution="PT30M",
            time_column_name="a_time",
            processing_level=ProcessingLevel.RAW,
        )

        expected_query = """
            SELECT a_time, COLUMNS(c -> c IN ('a_column_name'))
            FROM read_parquet(
                's3://a_bucket/a_network/dataset=a_data/site=A_SITE/**/date=*/data.parquet', hive_partitioning=true
            )
            WHERE
                (date BETWEEN ? AND ?);
        """

        result = router.query_by_date_range(container, start_date=start, end_date=end)
        call_query, call_params = mock_reader.read.call_args.args

        assert_frame_equal(result, TEST_DF)  # Return what the mock_reader returned
        assert call_query.strip() == expected_query.strip()
        assert call_params == [start, end]

    def test_query_by_date_range_builds_columns_lambda_for_multiple_containers(
        self, router: S3DataRouter, mock_reader: MagicMock
    ) -> None:
        """Tests that every container's source column is included in the COLUMNS(...) predicate."""
        start = datetime(2023, 1, 1)
        end = datetime(2023, 1, 2)

        container_1 = MagicMock(
            source_bucket="a_bucket",
            source_dataset="a_data",
            network="a_network",
            source_column="col_one",
            source_site_identifier="A_SITE",
            resolution="PT30M",
            time_column_name="a_time",
            processing_level=ProcessingLevel.RAW,
        )
        container_2 = MagicMock(
            source_bucket="a_bucket",
            source_dataset="a_data",
            network="a_network",
            source_column="col_two",
            source_site_identifier="A_SITE",
            resolution="PT30M",
            time_column_name="a_time",
            processing_level=ProcessingLevel.RAW,
        )

        router.query_by_date_range(container_1, container_2, start_date=start, end_date=end)
        call_query, _ = mock_reader.read.call_args.args

        assert "COLUMNS(c -> c IN ('col_one', 'col_two'))" in call_query

    @pytest.mark.parametrize("prefix", ["a", "b"])
    def test_read_from_partitioned_directory(self, prefix: str, s3_storage_client: S3StorageClient) -> None:
        """Tests reading from different partition structures, e.g. extra partition between site and date"""

        start = datetime(2023, 1, 1)
        end = datetime(2023, 1, 1)

        reader = DuckDBParquetReader(create_duckdb_factory())
        raw_reader = MagicMock(spec=RawFileReader)
        router = S3DataRouter(reader, raw_reader)

        container = MagicMock(
            source_bucket=E2E_INPUT_BUCKET,
            source_dataset=f"{prefix}_data",
            network=f"{prefix}_network",
            source_column="value",
            source_site_identifier=f"{prefix.upper()}_SITE",
            resolution="PT30M",
            time_column_name="time",
        )

        expected = pl.DataFrame(
            {
                "time": [datetime(2023, 1, 1), datetime(2023, 1, 1, 1), datetime(2023, 1, 1, 2)],
                "value": [1.23, 45.6, 7.89],
            }
        )

        result = router.query_by_date_range(container, start_date=start, end_date=end)

        assert_frame_equal(result, expected)

    def test_missing_column_is_dropped_without_failing_other_containers(
        self, s3_storage_client: S3StorageClient
    ) -> None:
        """Tests that a source_column not present in the parquet files is silently omitted from the result,
        rather than raising and losing every other container queried in the same group.
        """
        start = datetime(2023, 1, 1)
        end = datetime(2023, 1, 1)

        reader = DuckDBParquetReader(create_duckdb_factory())
        raw_reader = MagicMock(spec=RawFileReader)
        router = S3DataRouter(reader, raw_reader)

        existing_column_container = MagicMock(
            source_bucket=E2E_INPUT_BUCKET,
            source_dataset="a_data",
            network="a_network",
            source_column="value",
            source_site_identifier="A_SITE",
            resolution="PT30M",
            time_column_name="time",
        )
        missing_column_container = MagicMock(
            source_bucket=E2E_INPUT_BUCKET,
            source_dataset="a_data",
            network="a_network",
            source_column="does_not_exist",
            source_site_identifier="A_SITE",
            resolution="PT30M",
            time_column_name="time",
        )

        result = router.query_by_date_range(
            existing_column_container, missing_column_container, start_date=start, end_date=end
        )

        assert "value" in result.columns
        assert "does_not_exist" not in result.columns
        assert not result.is_empty()


class TestSitePartitionPrefix:
    def test_builds_raw_partition_path(self) -> None:
        """Tests that the raw dataset hive-partition path is built correctly."""
        result = S3DataRouter._site_partition_prefix("fdri", "dataset", "raw_flux", "SITE1")
        assert result == "fdri/dataset=raw_flux/site=SITE1"

    def test_builds_processed_partition_path(self) -> None:
        """Tests that the processed dataset hive-partition path uses the resolution key."""
        result = S3DataRouter._site_partition_prefix("fdri", "resolution", "P1D", "SITE1")
        assert result == "fdri/resolution=P1D/site=SITE1"


class TestStageLocally:
    def test_calls_download_once_per_day_in_range(self, router: S3DataRouter, mock_raw_reader: MagicMock) -> None:
        """Tests that download is called once for each day in the date range, inclusive."""
        mock_raw_reader.download.return_value = []
        container = MagicMock(
            s3_bucket="my-bucket",
            s3_dataset_path="fdri/dataset=raw_flux/site=SITE1",
            source_site_identifier="SITE1",
            ts_id="ds-1",
        )

        router.stage_locally(container, start_date=datetime(2024, 1, 1), end_date=datetime(2024, 1, 3))

        assert mock_raw_reader.download.call_count == 3

    def test_single_day_range_calls_download_once(self, router: S3DataRouter, mock_raw_reader: MagicMock) -> None:
        """Tests that a single-day range (start == end) results in exactly one download call."""
        mock_raw_reader.download.return_value = []
        container = MagicMock(
            s3_bucket="my-bucket",
            s3_dataset_path="fdri/dataset=raw_flux/site=SITE1",
            source_site_identifier="SITE1",
            ts_id="ds-1",
        )

        router.stage_locally(container, start_date=datetime(2024, 1, 1), end_date=datetime(2024, 1, 1))

        assert mock_raw_reader.download.call_count == 1

    def test_builds_correct_date_prefix_per_day(self, router: S3DataRouter, mock_raw_reader: MagicMock) -> None:
        """Tests that each download call uses the correct date-partitioned prefix."""
        mock_raw_reader.download.return_value = []
        container = MagicMock(
            s3_bucket="my-bucket",
            s3_dataset_path="fdri/dataset=raw_flux/site=SITE1",
            source_site_identifier="SITE1",
            ts_id="ds-1",
        )

        router.stage_locally(container, start_date=datetime(2024, 1, 1), end_date=datetime(2024, 1, 2))

        call_prefixes = [call.args[1] for call in mock_raw_reader.download.call_args_list]
        assert call_prefixes == [
            "fdri/dataset=raw_flux/site=SITE1/date=2024-01-01/",
            "fdri/dataset=raw_flux/site=SITE1/date=2024-01-02/",
        ]

    def test_returns_path_to_existing_local_directory(self, router: S3DataRouter, mock_raw_reader: MagicMock) -> None:
        """Tests that the returned path is a real directory that exists on disk."""
        mock_raw_reader.download.return_value = []
        container = MagicMock(source_site_identifier="SITE1", ts_id="ds-1")

        result = router.stage_locally(container, start_date=datetime(2024, 1, 1), end_date=datetime(2024, 1, 1))

        assert isinstance(result, Path)
        assert result.is_dir()

    def test_staged_directory_is_tracked_for_cleanup(self, router: S3DataRouter, mock_raw_reader: MagicMock) -> None:
        """Tests that the temp directory is added to the staged list so cleanup can remove it."""
        mock_raw_reader.download.return_value = []
        container = MagicMock(source_site_identifier="SITE1", ts_id="ds-1")

        router.stage_locally(container, start_date=datetime(2024, 1, 1), end_date=datetime(2024, 1, 1))

        assert len(router._staged) == 1


class TestCleanup:
    def test_cleanup_calls_cleanup_on_each_staged_dir(self, router: S3DataRouter) -> None:
        """Tests that cleanup is called on each tracked temp directory."""
        tmp1 = MagicMock()
        tmp2 = MagicMock()
        router._staged = [tmp1, tmp2]

        router.cleanup()

        tmp1.cleanup.assert_called_once()
        tmp2.cleanup.assert_called_once()

    def test_cleanup_empties_staged_list(self, router: S3DataRouter) -> None:
        """Tests that the staged list is empty after cleanup."""
        router._staged = [MagicMock(), MagicMock()]

        router.cleanup()

        assert router._staged == []
