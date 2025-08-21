import duckdb
import polars as pl

from datetime import datetime

from dritimeseriesprocessor.s3_crud.read import DuckDbParquetReader
from testing.utils.s3_test_helper import S3TestHelper


def get_unique_dates(df: pl.DataFrame):
    # Convert datetime to string date for easy assertion
    df = df.with_columns(pl.col('time').dt.strftime('%Y-%m-%d'))
    unique_dates = df.select('time').unique()
    return unique_dates

class TestReadParquetByQuery(S3TestHelper):
    def setUp(self):
        super().setUp()
        self.reader = DuckDbParquetReader()

        # Add some valid data to the bucket
        self.bucket_name = "ukceh-fdri-staging-timeseries-level-0"
        self.data = self._create_hourly_test_data(datetime(2024, 1, 1), datetime(2024, 1, 10), upload = True)

        # Add some corrupted data to the bucket
        self._put_object(self.bucket_name, "corrupted.parquet", b"corrupted data")

    def test_read_parquet_by_query_single_key(self):
        """ Test that a valid query on one object key returns the expected results
        """
        key = "cosmos/dataset=test_dataset/site=site1/date=2024-01-01/data.parquet"
        query = f"SELECT * FROM read_parquet('s3://{self.bucket_name}/{key}')"
        result = self.reader.read(query)

        self.assertIsInstance(result, pl.DataFrame)
        self.assertEqual(sorted(get_unique_dates(result)['time'].to_list()), ['2024-01-01'])

    def test_read_parquet_by_query_multiple_keys(self):
        """ Test that a valid query on multiple object keys returns the expected results
        """
        keys = ("cosmos/dataset=test_dataset/site=site1/date=2024-01-01/data.parquet",
                "cosmos/dataset=test_dataset/site=site1/date=2024-01-02/data.parquet")
        keys_str = [f's3://{self.bucket_name}/{key}' for key in keys]
        query = f"SELECT * FROM read_parquet({keys_str})"
        result = self.reader.read(query)

        self.assertIsInstance(result, pl.DataFrame)
        self.assertEqual(sorted(get_unique_dates(result)['time'].to_list()), ['2024-01-01', '2024-01-02'])

    def test_read_parquet_by_query_glob_keys(self):
        """ Test that a valid query using glob style key matching returns the expected results
        """
        query = f"SELECT * FROM read_parquet('s3://{self.bucket_name}/cosmos/dataset=test_dataset/site=*/date=*/data.parquet')"
        result = self.reader.read(query)

        self.assertIsInstance(result, pl.DataFrame)
        self.assertEqual(sorted(get_unique_dates(result)['time'].to_list()),
                         ['2024-01-01', '2024-01-02', '2024-01-03', '2024-01-04', '2024-01-05',
                          '2024-01-06', '2024-01-07', '2024-01-08', '2024-01-09', '2024-01-10'])

    def test_read_parquet_by_query_with_single_param(self):
        """ Test that a valid query including a parameterized WHERE clause returns the expected results
        """
        key = "cosmos/dataset=test_dataset/site=*/date=2024-01-01/data.parquet"
        query = f"SELECT * FROM read_parquet('s3://{self.bucket_name}/{key}') WHERE SITE_ID = ?"
        params = ['site1']
        result = self.reader.read(query, params)
        result_site_ids = result['SITE_ID'].unique().to_list()

        self.assertIsInstance(result, pl.DataFrame)
        self.assertEqual(sorted(get_unique_dates(result)['time'].to_list()), ['2024-01-01'])
        self.assertEqual(sorted(result_site_ids), ['site1'])

    def test_read_parquet_by_query_with_invalid_key_error(self):
        """ Test that an invalid key raises error
        """
        key = "non_existent_key.parquet"
        query = f"SELECT * FROM read_parquet('s3://{self.bucket_name}/{key}')"

        with self.assertRaises(duckdb.IOException):
            self.reader.read(query)

    def test_read_parquet_by_query_corrupt_error(self):
        """ Test that an error is raised if a corrupted parquet file is found
        """
        key = "corrupted.parquet"
        query = f"SELECT * FROM read_parquet('s3://{self.bucket_name}/{key}')"

        with self.assertRaises(duckdb.InvalidInputException):
            self.reader.read(query)

    def test_read_parquet_retry(self):
        """ Test that the retry decorator works as expected
        """
        key = "corrupted.parquet"
        query = f"SELECT * FROM read_parquet('s3://{self.bucket_name}/{key}')"

        with self.assertRaises(duckdb.InvalidInputException):
            self.reader.read(query)

        stats = self.reader.read.statistics
        self.assertEqual(stats['attempt_number'], 3)  # Should have tried 3 times
        self.assertEqual(stats['idle_for'], 4)  # Should have waited 2 seconds between each try
