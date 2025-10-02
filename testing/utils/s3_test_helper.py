"""Extension of TestHelper with additional functionality for test that require s3."""

import datetime
import io
import logging
from datetime import timedelta
from pathlib import Path
from typing import List

import boto3
import polars as pl
from botocore.exceptions import ClientError
from polars.testing import assert_frame_equal

from dritimeseriesprocessor.configuration import app_config
from testing.utils.base_test_helper import BaseTestHelper

logger = logging.getLogger(__name__)


class S3TestHelper(BaseTestHelper):
    def __init__(self) -> None:
        super().__init__()

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

    def _put_object(self, bucket_name: str, s3_key: str, body: bytes) -> None:
        """Uploads an object to an S3 bucket.

        Args:
            bucket_name: The name of the S3 bucket.
            s3_key: The key (path) of the object within the bucket.
            body: data to write to s3 object

        Raises:
            RuntimeError, ClientError: If there's any error
            in putting the object, error is logged and re raised

        """
        try:
            self.s3_client.put_object(Bucket=bucket_name, Key=s3_key, Body=body)
        except (RuntimeError, ClientError) as e:
            logger.error(f"Failed to put {s3_key} in {bucket_name}")
            logger.exception(e)
            raise e

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

            assert_frame_equal(actual_data, expected_data, check_column_order=False, check_dtypes=False)

    def _create_hourly_test_data(self, start_date: datetime, end_date: datetime, upload: bool = False) -> pl.DataFrame:
        """Create sample data that we have more control over for doing specific tests.

        Upload data to level 0 bucket with the expected partition structure if requested

        Args:
            start_date: The start date for the data
            end_date: The end date for the data
            upload: upload to the level 0 bucket
        """
        current_date = start_date

        all_data = {}

        while current_date <= end_date:
            for site in ["site1", "site2"]:
                # Create hourly data for the current date
                data = {
                    "time": [current_date + timedelta(hours=i) for i in range(24)] * 2,
                    "SITE_ID": [site] * 48,
                    "col1": list(range(48)),
                    "col2": list(range(48, 96)),
                }

                # upload to s3
                if upload:
                    # convert dataframe to parquet
                    df = pl.DataFrame(data)
                    parquet_buffer = io.BytesIO()
                    df.write_parquet(parquet_buffer)
                    parquet_buffer.seek(0)

                    # set the key
                    key = (
                        f"cosmos/dataset=test_dataset/site={site}/date={current_date.strftime('%Y-%m-%d')}/data.parquet"
                    )
                    bucket_name = "ukceh-fdri-staging-timeseries-level-0"

                    self._put_object(bucket_name, key, parquet_buffer.getvalue())

                all_data = all_data | data

            current_date += timedelta(days=1)

        return pl.DataFrame(all_data)
