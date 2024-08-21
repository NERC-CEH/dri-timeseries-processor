import os

import duckdb
import polars as pl
import unittest
from botocore.exceptions import ClientError

from dritimeseriesprocessor.s3_crud.read import DuckDbParquetReader
from tests.s3_crud.base_test_case import BaseTestCase
import moto

def get_unique_dates(df: pl.DataFrame):
    # Convert datetime to string date for easy assertion
    df = df.with_columns(pl.col('time').dt.strftime('%Y-%m-%d'))
    unique_dates = df.select('time').unique()
    return unique_dates

class TestReadParquetByQuery(BaseTestCase):
    def setUp(self):
        self.reader = DuckDbParquetReader()

    def test_read_parquet_by_query_single_key(self):
        """ Test that a valid query on one object key returns the expected results
        """
        key = "TEST_CATEGORY/2024-01/2024-01-01.parquet"
        query = f"SELECT * FROM read_parquet('s3://{self.bucket_name}/{key}')"
        result = self.reader.read(query)

        self.assertIsInstance(result, pl.DataFrame)
        self.assertEqual(sorted(get_unique_dates(result)['time'].to_list()), ['2024-01-01'])

    def test_read_parquet_by_query_multiple_keys(self):
        """ Test that a valid query on multiple object keys returns the expected results
        """
        keys = ("TEST_CATEGORY/2024-01/2024-01-01.parquet",
                "TEST_CATEGORY/2024-01/2024-01-02.parquet")
        keys_str = [f's3://{self.bucket_name}/{key}' for key in keys]
        query = f"SELECT * FROM read_parquet({keys_str})"
        result = self.reader.read(query)

        self.assertIsInstance(result, pl.DataFrame)
        self.assertEqual(sorted(get_unique_dates(result)['time'].to_list()), ['2024-01-01', '2024-01-02'])

    def test_read_parquet_by_query_glob_keys(self):
        """ Test that a valid query using glob style key matching returns the expected results
        """
        query = f"SELECT * FROM read_parquet('s3://{self.bucket_name}/TEST_CATEGORY/**/*.parquet')"
        result = self.reader.read(query)

        self.assertIsInstance(result, pl.DataFrame)
        self.assertEqual(sorted(get_unique_dates(result)['time'].to_list()),
                         ['2024-01-01', '2024-01-02', '2024-01-03', '2024-01-04', '2024-01-05',
                          '2024-01-06', '2024-01-07', '2024-01-08', '2024-01-09', '2024-01-10'])

    def test_read_parquet_by_query_with_single_param(self):
        """ Test that a valid query including a parameterized WHERE clause returns the expected results
        """
        key = "TEST_CATEGORY/2024-01/2024-01-01.parquet"
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

        with self.assertRaises(duckdb.HTTPException):
            self.reader.read(query)

    def test_read_parquet_by_query_corrupt_error(self):
        """ Test that an error is raised if a corrupted parquet file is found
        """
        key = "corrupted.parquet"
        query = f"SELECT * FROM read_parquet('s3://{self.bucket_name}/{key}')"

        with self.assertRaises(duckdb.InvalidInputException):
            self.reader.read(query)
