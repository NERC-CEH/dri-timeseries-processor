from datetime import date
import io
import unittest
from unittest.mock import patch

import boto3
import moto
import polars as pl

from dritimeseriesprocessor.parquet_access import get_parquet_by_dates


@moto.mock_aws
class TestGetParquetByDates(unittest.TestCase):
    def setUp(self):
        self.s3_client = boto3.client("s3")

        # Create a test bucket
        self.bucket_name = "test-bucket"
        self.s3_client.create_bucket(Bucket=self.bucket_name,
                                     CreateBucketConfiguration={"LocationConstraint": "eu-west-2"})
        # Add test Parquet files to the bucket
        self.add_test_parquet_files()

        # Create a test empty bucket
        self.empty_bucket_name = "empty-bucket"
        self.s3_client.create_bucket(Bucket=self.empty_bucket_name,
                                     CreateBucketConfiguration={"LocationConstraint": "eu-west-2"})

    def add_test_parquet_files(self):
        # Create some test Parquet dataframes and upload them as Parquet files to S3
        dates = ['2024-01-01', '2024-01-02', '2024-01-03', '2024-01-10']
        for d in dates:
            df = pl.DataFrame({
                'column1': [1, 2, 3],
                'column2': [4, 5, 6],
                'date': [d, d, d]
            })
            file_key = f'{d}.parquet'
            parquet_buffer = io.BytesIO()
            df.write_parquet(parquet_buffer)
            parquet_buffer.seek(0)
            self.s3_client.put_object(Bucket=self.bucket_name, Key=file_key, Body=parquet_buffer.getvalue())

    def test_read_parquet_files_in_date_range(self):
        """ Test that a Dataframe is returned containing all dates from requested data range where we know all
        dates exist
        """
        start_date = date(2024, 1, 1)
        end_date = date(2024, 1, 3)

        with patch('dritimeseriesprocessor.parquet_access.S3_CLIENT', self.s3_client):
            df = get_parquet_by_dates(self.bucket_name, start_date, end_date)

        unique_dates = df.select('date').unique()
        self.assertEqual(sorted(unique_dates['date'].to_list()), ['2024-01-01', '2024-01-02', '2024-01-03'])

    def test_read_parquet_files_in_date_range_no_files(self):
        """ Test that an empty Dataframe is returned when requesting dates that all don't have any data
        """
        start_date = date(2024, 1, 4)
        end_date = date(2024, 1, 6)

        with patch('dritimeseriesprocessor.parquet_access.S3_CLIENT', self.s3_client):
            df = get_parquet_by_dates(self.bucket_name, start_date, end_date)

        self.assertTrue(df.is_empty())

    def test_read_parquet_files_in_date_range_some_files(self):
        """ Test that a Dataframe is returned containing all dates from requested data range that includes gaps
        """
        start_date = date(2024, 1, 1)
        end_date = date(2024, 1, 20)

        with patch('dritimeseriesprocessor.parquet_access.S3_CLIENT', self.s3_client):
            df = get_parquet_by_dates(self.bucket_name, start_date, end_date)

        unique_dates = df.select('date').unique()
        self.assertEqual(sorted(unique_dates['date'].to_list()),
                         ['2024-01-01', '2024-01-02', '2024-01-03', '2024-01-10'])

    def test_invalid_date_range(self):
        """ Test that error is raised if invalid date range given
        """
        start_date = date(2024, 1, 5)
        end_date = date(2024, 1, 1)

        with self.assertRaises(UserWarning):
            get_parquet_by_dates(self.bucket_name, start_date, end_date)

    def test_corrupted_parquet_file(self):
        """ Test that an error is raised if a corrupted parquet file is found
        """
        start_date = date(2024, 1, 1)
        end_date = date(2024, 1, 11)

        self.s3_client.put_object(Bucket=self.bucket_name,
                                  Key='2024-01-11.parquet',
                                  Body=b'corrupted data')

        with patch('dritimeseriesprocessor.parquet_access.S3_CLIENT', self.s3_client):
            with self.assertRaises(pl.exceptions.ComputeError):
                get_parquet_by_dates(self.bucket_name, start_date, end_date)

    def test_empty_bucket(self):
        """ Test that an empty bucket returns nothing
        """
        start_date = date(2024, 1, 1)
        end_date = date(2024, 1, 3)

        with patch('dritimeseriesprocessor.parquet_access.S3_CLIENT', self.s3_client):
            df = get_parquet_by_dates(self.empty_bucket_name, start_date, end_date)

        self.assertTrue(df.is_empty())
