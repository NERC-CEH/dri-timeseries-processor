"""Extension of TestHelper with additional functionality for test that require s3."""

import glob
import logging
from pathlib import Path
from polars.testing import assert_frame_equal
from typing import List

import boto3
import polars as pl
from botocore.exceptions import ClientError

from dritimeseriesprocessor.configuration import app_config
from testing.utils.base_test_helper import BaseTestHelper

logger = logging.getLogger(__name__)


class S3TestHelper(BaseTestHelper):
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

    def _count_s3_keys(self, bucket_name: str) -> List[str]:
        """
        Count the objects in S3 for the provided bucket.

        Never > 1000 objects whilst testing (I hope!) so not using paginators.

        Args:
            bucket_name: Name of the bucket to list objects for.

        Returns:
            List of S3 Keys

        """
        s3_items = self.s3_client.list_objects_v2(Bucket=bucket_name).get("Contents", [])
        return len(s3_items)

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

    def _check_expected_parquet_files_exist_in_bucket(self, expected_base_dir: str, output_bucket_name: str) -> None:
        """Check the s3 bucket contains only the expected outputs
        
        Check that for every expected parquet file, the corresponding parquet has been
        generated with a matching path structure (i.e. same s3 keys) and contents, and no
        other parquet files have been generated
        
        Args:
            expected_base_dir: The base directory where the expected outputs are stored
            output_bucket_name: The s3 bucket name where processor outputs are written
        """
        number_of_s3_objects = self._count_s3_keys(output_bucket_name)
        number_of_expected_outputs = len([output for output in expected_base_dir.rglob("data.parquet")])

        assert number_of_s3_objects == number_of_expected_outputs

        for expected_path in expected_base_dir.rglob("data.parquet"):
            expected_s3_key = str(expected_path.relative_to(expected_base_dir))
            actual_data = pl.read_parquet(self._get_s3_object(bucket_name=output_bucket_name, s3_key=expected_s3_key))
            expected_data = self._read_expected_data(s3_key=expected_s3_key, expected_base_dir=expected_base_dir)

            assert_frame_equal(actual_data, expected_data)
