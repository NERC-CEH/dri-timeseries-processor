from datetime import datetime
from typing import Iterator
from unittest.mock import MagicMock

import duckdb
import polars as pl
import pytest
from polars.testing import assert_frame_equal

from dritimeseriesprocessor.configuration.app_config import app_config
from dritimeseriesprocessor.io_backend.duckdb_connection import DuckDBConnectionFactory, create_duckdb_factory
from dritimeseriesprocessor.io_backend.reader import DuckDBParquetReader
from dritimeseriesprocessor.storage.storage_client import S3StorageClient
from utils.s3_test_helpers import create_hourly_test_data
from utils.validation_helpers import assert_unique_dates_in_dataframe

DUMMY_DF = pl.DataFrame({"a": [1]})


@pytest.fixture
def s3_storage_client() -> S3StorageClient:
    cfg = app_config()
    client = S3StorageClient(cfg.AWS_ACCESS_KEY_ID, cfg.AWS_SECRET_ACCESS_KEY, cfg.AWS_DEFAULT_REGION, cfg.endpoint_url)
    return client


@pytest.fixture
def mock_conn() -> MagicMock:
    conn = MagicMock()
    # Return a dummy Polars DataFrame
    conn.execute.return_value.pl.return_value = DUMMY_DF.clone()
    return conn


@pytest.fixture
def mock_factory(mock_conn: MagicMock) -> MagicMock:
    """A mock factory that returns the mock connection."""
    factory = MagicMock(spec=DuckDBConnectionFactory)
    factory.create.return_value = mock_conn
    return factory


class TestDuckDBParquetReader:
    """Simple tests that check the core functionality of the class"""

    def test_read_calls_factory_create(self, mock_factory: MagicMock) -> None:
        reader = DuckDBParquetReader(connection_factory=mock_factory)
        result = reader.read("SELECT 1")

        mock_factory.create.assert_called_once()
        assert_frame_equal(result, DUMMY_DF)

    def test_read_executes_query(self, mock_factory: MagicMock, mock_conn: MagicMock) -> None:
        reader = DuckDBParquetReader(connection_factory=mock_factory)
        result = reader.read("SELECT * FROM tbl", params=[123])

        mock_conn.execute.assert_called_once()
        mock_conn.execute.assert_called_with("SELECT * FROM tbl", [123])
        assert_frame_equal(result, DUMMY_DF)

    def test_retry_on_invalid_input_second_passes(self, mock_factory: MagicMock, mock_conn: MagicMock) -> None:
        """Test that the second retry is a success"""
        mock_conn.execute.side_effect = [duckdb.InvalidInputException(), MagicMock(pl=lambda: DUMMY_DF)]

        reader = DuckDBParquetReader(connection_factory=mock_factory)
        result = reader.read("SELECT * FROM tbl")

        assert mock_conn.execute.call_count == 2
        assert_frame_equal(result, DUMMY_DF)

        stats = reader.read.statistics  # type: ignore[attr-defined]
        assert stats["attempt_number"] == 2
        assert stats["idle_for"] == 2

    def test_retry_on_invalid_input_all_fail(self, mock_factory: MagicMock, mock_conn: MagicMock) -> None:
        """Test that max number of retries occurs on raising a InvalidInputException"""
        mock_conn.execute.side_effect = duckdb.InvalidInputException()
        reader = DuckDBParquetReader(connection_factory=mock_factory)

        with pytest.raises(duckdb.InvalidInputException):
            reader.read("SELECT * FROM tbl")

        assert mock_conn.execute.call_count == 3

        stats = reader.read.statistics  # type: ignore[attr-defined]
        assert stats["attempt_number"] == 3
        assert stats["idle_for"] == 4

    def test_retry_on_http_exception(self, mock_factory: MagicMock, mock_conn: MagicMock) -> None:
        """Test that retry doesn't occur on raising a HTTPException"""
        mock_conn.execute.side_effect = duckdb.HTTPException()
        reader = DuckDBParquetReader(connection_factory=mock_factory)

        with pytest.raises(duckdb.HTTPException):
            reader.read("SELECT * FROM tbl")

        assert mock_conn.execute.call_count == 1

        stats = reader.read.statistics  # type: ignore[attr-defined]
        assert stats["attempt_number"] == 1
        assert stats["idle_for"] == 0


BUCKET_NAME = "ukceh-dri-staging-ingested"


@pytest.fixture
def reader() -> DuckDBParquetReader:
    factory = create_duckdb_factory()
    return DuckDBParquetReader(factory)


@pytest.fixture
def setup_test_data(s3_storage_client: S3StorageClient) -> Iterator:
    # setup
    s3_storage_client.clear_bucket(BUCKET_NAME)
    create_hourly_test_data(
        start=datetime(2024, 1, 1),
        end=datetime(2024, 1, 10),
        bucket_name=BUCKET_NAME,
        upload=True,
        storage_client=s3_storage_client,
    )
    s3_storage_client.put_bytes(BUCKET_NAME, "corrupted.parquet", b"corrupted data")

    yield

    # teardown
    s3_storage_client.clear_bucket(BUCKET_NAME)


@pytest.mark.usefixtures("setup_test_data")
class TestDuckDBParquetReaderIntegration:
    """Integration tests that check specific usages of the class"""

    @pytest.mark.parametrize(
        "keys, expected",
        [
            (("cosmos/dataset=test_dataset/site=site1/date=2024-01-01/data.parquet",), ["2024-01-01"]),
            (
                (
                    "cosmos/dataset=test_dataset/site=site1/date=2024-01-01/data.parquet",
                    "cosmos/dataset=test_dataset/site=site1/date=2024-01-02/data.parquet",
                ),
                ["2024-01-01", "2024-01-02"],
            ),
        ],
    )
    def test_read_parquet_valid(self, keys: tuple, expected: list, reader: DuckDBParquetReader) -> None:
        """Happy-path: read parquet key(s) via DuckDB and return expected dates."""
        keys_str = [f"s3://{BUCKET_NAME}/{key}" for key in keys]
        query = f"SELECT * FROM read_parquet({keys_str})"

        result = reader.read(query)
        assert isinstance(result, pl.DataFrame)
        assert_unique_dates_in_dataframe(result, expected)

    def test_read_parquet_by_query_glob_keys(self, reader: DuckDBParquetReader) -> None:
        """Test that a valid query using glob style key matching returns the expected results"""
        query = (
            f"SELECT * FROM read_parquet('s3://{BUCKET_NAME}/cosmos/dataset=test_dataset/site=*/date=*/data.parquet')"
        )
        result = reader.read(query)
        expected = [
            "2024-01-01",
            "2024-01-02",
            "2024-01-03",
            "2024-01-04",
            "2024-01-05",
            "2024-01-06",
            "2024-01-07",
            "2024-01-08",
            "2024-01-09",
            "2024-01-10",
        ]
        assert isinstance(result, pl.DataFrame)
        assert_unique_dates_in_dataframe(result, expected)

    def test_read_parquet_by_query_with_single_param(self, reader: DuckDBParquetReader) -> None:
        """Test that a valid query including a parameterized WHERE clause returns the expected results"""
        key = "cosmos/dataset=test_dataset/site=*/date=2024-01-01/data.parquet"
        query = f"SELECT * FROM read_parquet('s3://{BUCKET_NAME}/{key}') WHERE SITE_ID = ?"
        params = ["site1"]
        result = reader.read(query, params)
        result_site_ids = result["SITE_ID"].unique().to_list()

        assert isinstance(result, pl.DataFrame)
        assert_unique_dates_in_dataframe(result, ["2024-01-01"])
        assert sorted(result_site_ids) == ["site1"]

    def test_read_parquet_by_query_with_invalid_key_error(self, reader: DuckDBParquetReader) -> None:
        """Test that an invalid key raises error"""
        key = "non_existent_key.parquet"
        query = f"SELECT * FROM read_parquet('s3://{BUCKET_NAME}/{key}')"
        with pytest.raises(duckdb.IOException):
            reader.read(query)

    def test_read_parquet_by_query_corrupt_error(self, reader: DuckDBParquetReader) -> None:
        """Test that an error is raised if a corrupted parquet file is found"""
        key = "corrupted.parquet"
        query = f"SELECT * FROM read_parquet('s3://{BUCKET_NAME}/{key}')"
        with pytest.raises(duckdb.InvalidInputException):
            reader.read(query)

    def test_read_parquet_retry(self, reader: DuckDBParquetReader) -> None:
        """Test that the retry decorator works as expected"""
        key = "corrupted.parquet"
        query = f"SELECT * FROM read_parquet('s3://{BUCKET_NAME}/{key}')"

        with pytest.raises(duckdb.InvalidInputException):
            reader.read(query)

        stats = reader.read.statistics  # type: ignore[attr-defined]
        assert stats["attempt_number"] == 3  # Should have tried 3 times
        assert stats["idle_for"] == 4  # Should have waited 2 seconds between each try
