"""Module for handling data writing logic"""

import logging
from abc import ABC, abstractmethod
from datetime import datetime
from io import BytesIO

import polars as pl
from botocore.client import BaseClient
from mypy_boto3_s3.client import S3Client
from polars.dataframe import DataFrame
from polars.dataframe.group_by import GroupBy

from dritimeseriesprocessor.metrics_exporter import metrics

logger = logging.getLogger(__name__)


class WriterInterface(ABC):
    """Interface for defining parquet writing objects"""

    @abstractmethod
    def write(self, *args, **kwargs) -> None:
        """Abstract method for read operations"""


class S3Writer(WriterInterface):
    """Writes to an S3 bucket"""

    s3_client: S3Client
    """Handle to the the s3 client used to read data"""

    def __init__(self, s3_client: S3Client):
        """Initializes the class

        Args:
            s3_client: The s3 client used to retrieve data from
        """

        if not isinstance(s3_client, BaseClient):
            raise TypeError(f"`s3_client` must be a `S3Client` not `{type(s3_client)}`")

        self.s3_client = s3_client

    @staticmethod
    def _get_bytes(obj: DataFrame) -> bytes:
        """Converts an object to bytes

        Args:
            obj: The object to convert.
        Returns:
            bytes representation of the object.
        """

        buffer = BytesIO()

        if isinstance(obj, pl.dataframe.DataFrame):
            obj.write_parquet(buffer)
        else:
            raise TypeError(f"Bytes conversion not supported for type: '{type(obj)}'")

        buffer.seek(0)

        return buffer

    @metrics.track_s3_write_time()
    def write(self, bucket_name: str, dataset: str, data: GroupBy) -> None:
        """Uploads objects to an S3 bucket.

        This function attempts to upload objects to a specified S3 bucket
        using the provided S3 client. Objects are converted to bytes.
        If the upload fails, it logs an error message and re-raises the exception.

        Args:
            bucket_name: The name of the S3 bucket.
            dataset: The dataset which the data sits in.
            data: data to write to s3 object

        Raises:
            RuntimeError, ClientError
        """

        for date, site_id, df in data:
            s3_key = self._build_s3_key(dataset, site_id, date)

            body = self._get_bytes(df)

            self.s3_client.put_object(Bucket=bucket_name, Key=s3_key, Body=body)

    @staticmethod
    def _build_s3_key(dataset: str, site_id: str, date: datetime) -> str:
        """Builds a S3 key.

        dataset=<dataset>/site=<site_id>/date=<date>/data.parquet

        Args:
            dataset: The dataset the data comes from
            site_id: The site_id the data comes from
            date: The date the data comes from

        Returns:
            A string of the key
        """

        day = date.strftime("%Y-%m-%d")

        return f"cosmos/dataset={dataset}/site={site_id}/date={day}/data.parquet"
