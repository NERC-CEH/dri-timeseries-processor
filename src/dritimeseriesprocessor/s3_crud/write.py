"""Module for handling data writing logic"""

import logging
from abc import ABC, abstractmethod
from datetime import date
from io import BytesIO

import polars as pl
from botocore.client import BaseClient
from mypy_boto3_s3.client import S3Client
from polars.dataframe import DataFrame

from dritimeseriesprocessor.utils import steralize_dates
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
    def write(self, bucket_name: str, key: str, body: bytes) -> None:
        """Uploads an object to an S3 bucket.

        This function attempts to upload a byte object to a specified S3 bucket
        using the provided S3 client. If the upload fails, it logs an error
        message and re-raises the exception.

        Args:
            bucket_name: The name of the S3 bucket.
            key: The key (path) of the object within the bucket.
            body: data to write to s3 object

        Raises:
            RuntimeError, ClientError
        """
        if not isinstance(body, bytes):
            body = self._get_bytes(body)

        self.s3_client.put_object(Bucket=bucket_name, Key=key, Body=body)

    @staticmethod
    def _build_date_range_key(start_date: date, end_date: date) -> str:
        """Builds an S3 key based on a date range

        Args:
            start_date: The start of the range
            end_date: The end of the range
        Returns:
            A string of the key
        Raises:
            TypeError
        """

        start_date, end_date = steralize_dates(start_date, end_date)

        date_format = r"%Y-%m-%d"

        return f"{start_date.strftime(date_format)}<=>{end_date.strftime(date_format)}"
