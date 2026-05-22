from datetime import datetime
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
        )

        expected_query = """
            SELECT a_time, "a_column_name"
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
