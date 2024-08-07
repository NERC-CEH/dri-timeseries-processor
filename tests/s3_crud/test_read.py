import unittest
from unittest.mock import patch
from pathlib import Path

import boto3
import moto
import polars as pl
from botocore.exceptions import ClientError

from dritimeseriesprocessor.s3_crud.read import read_parquet_by_key, read_parquet_by_query


@moto.mock_aws
class BaseTestCase(unittest.TestCase):
    def setUp(self):
        self.s3_client = boto3.client("s3", region_name="eu-west-2")

        # Create a test bucket to store parquet files
        self.bucket_name = "test-bucket"
        self.s3_client.create_bucket(Bucket=self.bucket_name,
                                     CreateBucketConfiguration={"LocationConstraint": "eu-west-2"})

        # Create a test empty bucket
        self.empty_bucket_name = "empty-bucket"
        self.s3_client.create_bucket(Bucket=self.empty_bucket_name,
                                     CreateBucketConfiguration={"LocationConstraint": "eu-west-2"})

        # Add test Parquet files to the bucket
        test_directory = Path("parquet-data")
        for file_path in test_directory.rglob("*.parquet"):
            self.s3_client.upload_file(
                Filename=str(file_path),
                Bucket=self.bucket_name,
                Key=str(file_path.relative_to(test_directory))
            )

#
# @moto.mock_aws
# class TestReadParquetByKey(BaseTestCase):
#     def test_read_parquet_by_key_success(self):
#         """ Test that a valid key returns the Parquet dataset
#         """
#         with patch("dritimeseriesprocessor.s3_crud.read.s3_client", self.s3_client):
#             key = "LEVEL_-1_SOILMET_1MIN_2024_LOOPED/2024-01/2024-01-21.parquet"
#             result = read_parquet_by_key(self.bucket_name, key)
#
#         self.assertIsInstance(result, pl.DataFrame)
#         self.assertFalse(result.is_empty())
#
#     def test_read_parquet_by_key_invalid_key_error(self):
#         """ Test that an invalid key raises error
#         """
#         with patch("dritimeseriesprocessor.s3_crud.read.s3_client", self.s3_client):
#             with self.assertRaises(ClientError):
#                 read_parquet_by_key(self.bucket_name, "non_existent_key")
#
#     def test_read_parquet_by_key_corrupt_error(self):
#         """ Test that an error is raised if a corrupted parquet file is found
#         """
#         self.s3_client.put_object(Bucket=self.bucket_name,
#                                   Key="corrupt.parquet",
#                                   Body=b"corrupted data")
#
#         with patch("dritimeseriesprocessor.s3_crud.read.s3_client", self.s3_client):
#             with self.assertRaises(pl.exceptions.ComputeError):
#                 read_parquet_by_key(self.bucket_name, "corrupt.parquet")


@moto.mock_aws
class TestReadParquetByQuery(BaseTestCase):
    def test_read_parquet_by_query_single_key_success(self):
        """ Test that a valid query on one object key returns the expected results
        """
        with patch("dritimeseriesprocessor.s3_crud.read.s3_client", self.s3_client):
            with patch("dritimeseriesprocessor.s3_crud.read.app_config.endpoint_url", "http://localhost:5000"):
                key = "LEVEL_-1_SOILMET_1MIN_2024_LOOPED/2024-01/2024-01-21.parquet"
                query = f"SELECT * FROM read_parquet('s3://{self.bucket_name}/{key}')"
                result = read_parquet_by_query(query)

        self.assertIsInstance(result, pl.DataFrame)
        self.assertFalse(result.is_empty())
