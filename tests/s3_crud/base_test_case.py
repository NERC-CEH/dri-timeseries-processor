import io
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

import boto3
import polars as pl


class BaseTestCase(unittest.TestCase):
    """ Unit testing of DuckDb requires connecting to the localstack server, rather than using Moto.
    Whatever DuckDb does to connect to S3 is not handled within the Moto mocking setup, so you get the error:
    "duckdb.duckdb.IOException: IO Error: Connection error for HTTP HEAD to http://localhost:5000/test-bucket..."
    """
    @classmethod
    def setUpClass(cls):
        cls.s3_client = boto3.client("s3", endpoint_url="http://localhost:4566", region_name="eu-west-2")

        # Define some bucket names
        cls.bucket_name = "test-bucket"
        cls.empty_bucket_name = "empty-bucket"
        
        # First, clear any hangovers from previous tests that may not have cleared up properly
        cls.clear_buckets()

        # Create a test bucket to store parquet files
        cls.s3_client.create_bucket(Bucket=cls.bucket_name,
                                    CreateBucketConfiguration={"LocationConstraint": "eu-west-2"})

        # Create a test empty bucket
        cls.s3_client.create_bucket(Bucket=cls.empty_bucket_name,
                                    CreateBucketConfiguration={"LocationConstraint": "eu-west-2"})

        # Add test Parquet files to the bucket
        cls.create_and_upload_test_data()

        # Add some corrupt data for testing
        cls.s3_client.put_object(Bucket=cls.bucket_name, Key="corrupted.parquet", Body=b"corrupted data")

        # Patch the s3 client
        cls.patch_s3_client = patch("dritimeseriesprocessor.s3_crud.read.s3_client", cls.s3_client)

    @classmethod
    def tearDownClass(cls):
        # Clear the buckets
        cls.clear_buckets()

        # Stop the patches
        cls.patch_s3_client.stop()

    @classmethod
    def clear_buckets(cls):
        # Clear the buckets from the localstack instance
        buckets = (cls.bucket_name, cls.empty_bucket_name)
        for bucket_name in buckets:
            try:
                # Delete all objects in the bucket
                bucket = cls.s3_client.list_objects(Bucket=bucket_name)
                if 'Contents' in bucket:
                    for obj in bucket['Contents']:
                        cls.s3_client.delete_object(Bucket=bucket_name, Key=obj['Key'])
                # Delete the bucket
                cls.s3_client.delete_bucket(Bucket=bucket_name)
            except cls.s3_client.exceptions.NoSuchBucket:
                pass

    @classmethod
    def create_and_upload_test_data(cls):
        # Create sample data that we have more control over for doing specific tests
        start_date = datetime(2024, 1, 1)
        end_date = datetime(2024, 1, 10)
        current_date = start_date

        while current_date <= end_date:
            # Create hourly data for the current date
            data = {
                'time': [current_date + timedelta(hours=i) for i in range(24)] * 2,
                'SITE_ID': ['site1'] * 24 + ['site2'] * 24,
                'col1': list(range(48)),
                'col2': list(range(48, 96))
            }
            df = pl.DataFrame(data)

            # Convert DataFrame to Parquet
            parquet_buffer = io.BytesIO()
            df.write_parquet(parquet_buffer)
            parquet_buffer.seek(0)

            # Upload Parquet file to S3 bucket with date-stamped filename
            file_key = f"TEST_CATEGORY/TEST_YEAR/TEST_MONTH/{current_date.strftime('%Y-%m-%d')}.parquet"
            cls.s3_client.put_object(Bucket=cls.bucket_name, Key=file_key, Body=parquet_buffer.getvalue())

            current_date += timedelta(days=1)

if __name__ == "__main__":
    unittest.main()