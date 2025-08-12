"""Extension of TestHelper with additional functionality for test that require s3."""

import io
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import List

import boto3
import polars as pl
from botocore.exceptions import ClientError

from dritimeseriesprocessor.configuration import app_config
from testing.utils.base_test_helper import BaseTestHelper

logger = logging.getLogger(__name__)


class s3TestHelper(BaseTestHelper):
    def setUp(self) -> None:
        super().setUp()

        # Don't allow tests to be run unless the environment is set to local in order to
        # prevent accidental changes to the staging or production environments
        if not app_config.environment == "local":
            raise RuntimeError("Localstack must be used to run tests that access S3")

        self.s3_client = boto3.client("s3", endpoint_url=app_config.endpoint_url)

        self._clear_bucket_data(app_config.processed_bucket)

    def _list_s3_keys(self, bucket_name: str) -> List[str]:
        """
        List the available objects from S3 for the provided bucket.

        Args:
            bucket_name: Name of the bucket to list objects for.

        Returns:
            List of S3 Keys

        """
        s3_items = self.s3_client.list_objects_v2(Bucket=bucket_name).get("Contents", [])
        return [item["Key"] for item in s3_items]

    def _get_s3_object(self, bucket_name: str, s3_key: str) -> bytes:
        """
        Retrieve an s3 object, reading its data.

        Args:
            bucket_name: Name of the bucket to use.
            s3_key: Key of the object to read from S3.

        Raises:
            e: Error raised during retrieving or reading the data from S3.

        Returns:
            Opened S3 data in bytes.

        """
        try:
            data = self.s3_client.get_object(Bucket=bucket_name, Key=s3_key)
            return data["Body"].read()
        except (RuntimeError, ClientError) as err:
            logger.error(f"Failed to get {s3_key} from {bucket_name}")
            logger.exception(err)
            raise err

    def _read_expected_data(self, s3_key: str, expected_base_dir: Path) -> pl.DataFrame:
        """
        Read the expected parquet data for the provided s3_key and base directory.

        It is assumed that the structure of the expected data matches that of the s3 store, therefore the expected
        data path will have the following structure: `expected_base_directory/network/date/site/resolution/data.parquet`

        Args:
            s3_key: Name of the s3 key used to store the data on s3 created during the test.
            expected_base_dir: Path to the expected data base directory.

        Returns:
            Dataframe containing the loaded expected data

        """
        expected_data_path = expected_base_dir / s3_key
        expected_data = pl.read_parquet(expected_data_path)

        return expected_data

    def _clear_bucket_data(self, bucket_name: str) -> None:
        """
        Remove all objects stored within the provided bucket

        Args:
            bucket_name: Name of the bucket to delete all objects from

        """
        for s3_key in self._list_s3_keys(bucket_name):
            self.s3_client.delete_object(Bucket=bucket_name, Key=s3_key)

    def _create_test_data(self, bucket_name: str):
        # Create sample data that we have more control over for doing specific tests
        start_date = datetime(2024, 1, 1)
        end_date = datetime(2024, 1, 10)
        current_date = start_date

        data = {}

        while current_date <= end_date:
            for site in ['site1', 'site2']:
                # Create hourly data for the current date
                data = data | {
                    'time': [current_date + timedelta(hours=i) for i in range(24)] * 2,
                    'SITE_ID': [site] * 48,
                    'col1': list(range(48)),
                    'col2': list(range(48, 96))
                }

            current_date += timedelta(days=1)
        
        return pl.DataFrame(data)
