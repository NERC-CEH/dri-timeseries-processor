from datetime import datetime

import duckdb
import polars as pl
import pytest

from dritimeseriesprocessor.s3_crud.read import DuckDbParquetReader
from testing.utils.s3_test_helper import S3TestHelper

BUCKET_NAME = "ukceh-fdri-staging-timeseries-level-0"


def get_unique_dates(df: pl.DataFrame) -> pl.Series:
    # Convert datetime to string date for easy assertion
    df = df.with_columns(pl.col("time").dt.strftime("%Y-%m-%d"))
    unique_dates = df.select("time").unique()
    return unique_dates


class TestReadParquetByQuery:
    def test_read_parquet_by_query_single_key(self, s3_test_helper: S3TestHelper) -> None:
        """Test that a valid query on one object key returns the expected results"""
        reader = DuckDbParquetReader()
        s3_test_helper._create_hourly_test_data(datetime(2024, 1, 1), datetime(2024, 1, 10), upload=True)
        s3_test_helper._put_object(BUCKET_NAME, "corrupted.parquet", b"corrupted data")

        key = "cosmos/dataset=test_dataset/site=site1/date=2024-01-01/data.parquet"
        query = f"SELECT * FROM read_parquet('s3://{BUCKET_NAME}/{key}')"
        result = reader.read(query)

        assert isinstance(result, pl.DataFrame)
        assert sorted(get_unique_dates(result)["time"].to_list()) == ["2024-01-01"]

    def test_read_parquet_by_query_multiple_keys(self, s3_test_helper: S3TestHelper) -> None:
        """Test that a valid query on multiple object keys returns the expected results"""
        reader = DuckDbParquetReader()
        s3_test_helper._create_hourly_test_data(datetime(2024, 1, 1), datetime(2024, 1, 10), upload=True)
        s3_test_helper._put_object(BUCKET_NAME, "corrupted.parquet", b"corrupted data")

        keys = (
            "cosmos/dataset=test_dataset/site=site1/date=2024-01-01/data.parquet",
            "cosmos/dataset=test_dataset/site=site1/date=2024-01-02/data.parquet",
        )
        keys_str = [f"s3://{BUCKET_NAME}/{key}" for key in keys]
        query = f"SELECT * FROM read_parquet({keys_str})"
        result = reader.read(query)

        assert isinstance(result, pl.DataFrame)
        assert sorted(get_unique_dates(result)["time"].to_list()) == ["2024-01-01", "2024-01-02"]

    def test_read_parquet_by_query_glob_keys(self, s3_test_helper: S3TestHelper) -> None:
        """Test that a valid query using glob style key matching returns the expected results"""
        reader = DuckDbParquetReader()
        s3_test_helper._create_hourly_test_data(datetime(2024, 1, 1), datetime(2024, 1, 10), upload=True)
        s3_test_helper._put_object(BUCKET_NAME, "corrupted.parquet", b"corrupted data")

        query = (
            f"SELECT * FROM read_parquet('s3://{BUCKET_NAME}/cosmos/dataset=test_dataset/site=*/date=*/data.parquet')"
        )
        result = reader.read(query)

        assert isinstance(result, pl.DataFrame)
        assert sorted(get_unique_dates(result)["time"].to_list()) == [
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

    def test_read_parquet_by_query_with_single_param(self, s3_test_helper: S3TestHelper) -> None:
        """Test that a valid query including a parameterized WHERE clause returns the expected results"""
        reader = DuckDbParquetReader()
        s3_test_helper._create_hourly_test_data(datetime(2024, 1, 1), datetime(2024, 1, 10), upload=True)
        s3_test_helper._put_object(BUCKET_NAME, "corrupted.parquet", b"corrupted data")

        key = "cosmos/dataset=test_dataset/site=*/date=2024-01-01/data.parquet"
        query = f"SELECT * FROM read_parquet('s3://{BUCKET_NAME}/{key}') WHERE SITE_ID = ?"
        params = ["site1"]
        result = reader.read(query, params)
        result_site_ids = result["SITE_ID"].unique().to_list()

        assert isinstance(result, pl.DataFrame)
        assert sorted(get_unique_dates(result)["time"].to_list()) == ["2024-01-01"]
        assert sorted(result_site_ids) == ["site1"]

    def test_read_parquet_by_query_with_invalid_key_error(self, s3_test_helper: S3TestHelper) -> None:
        """Test that an invalid key raises error"""
        reader = DuckDbParquetReader()
        s3_test_helper._create_hourly_test_data(datetime(2024, 1, 1), datetime(2024, 1, 10), upload=True)
        s3_test_helper._put_object(BUCKET_NAME, "corrupted.parquet", b"corrupted data")

        key = "non_existent_key.parquet"
        query = f"SELECT * FROM read_parquet('s3://{BUCKET_NAME}/{key}')"

        with pytest.raises(duckdb.IOException):
            reader.read(query)

    def test_read_parquet_by_query_corrupt_error(self, s3_test_helper: S3TestHelper) -> None:
        """Test that an error is raised if a corrupted parquet file is found"""
        reader = DuckDbParquetReader()
        s3_test_helper._create_hourly_test_data(datetime(2024, 1, 1), datetime(2024, 1, 10), upload=True)
        s3_test_helper._put_object(BUCKET_NAME, "corrupted.parquet", b"corrupted data")

        key = "corrupted.parquet"
        query = f"SELECT * FROM read_parquet('s3://{BUCKET_NAME}/{key}')"

        with pytest.raises(duckdb.InvalidInputException):
            reader.read(query)

    def test_read_parquet_retry(self, s3_test_helper: S3TestHelper) -> None:
        """Test that the retry decorator works as expected"""
        reader = DuckDbParquetReader()
        s3_test_helper._create_hourly_test_data(datetime(2024, 1, 1), datetime(2024, 1, 10), upload=True)
        s3_test_helper._put_object(BUCKET_NAME, "corrupted.parquet", b"corrupted data")

        key = "corrupted.parquet"
        query = f"SELECT * FROM read_parquet('s3://{BUCKET_NAME}/{key}')"

        with pytest.raises(duckdb.InvalidInputException):
            reader.read(query)

        stats = reader.read.statistics
        assert stats["attempt_number"] == 3  # Should have tried 3 times
        assert stats["idle_for"] == 4  # Should have waited 2 seconds between each try
