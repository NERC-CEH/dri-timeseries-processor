"""Module for writing parquet data"""

import logging
from abc import ABC, abstractmethod
from io import BytesIO

import polars as pl
from botocore.exceptions import ClientError

from dritimeseriesprocessor.storage.storage_client import S3StorageClient, StorageClient
from dritimeseriesprocessor.utils.polars_utils import merge_dataframes

logger = logging.getLogger(__name__)


class ParquetWriterInterface(ABC):
    """Interface for defining parquet writing objects"""

    @abstractmethod
    def write(self, *args, **kwargs) -> None:
        """Abstract method for write operations"""
        pass


class ByteParquetWriter(ParquetWriterInterface):
    """Parquet writer backed by a byte-level StorageClient (e.g. S3).

    This class handles:
    - Writing DataFrames as parquet bytes
    - Merging with existing parquet files
    - Splitting DataFrames into date partitions
    """

    def __init__(self, storage: StorageClient):
        self.storage = storage

    def write(self, bucket: str, key: str, df: pl.DataFrame, time_col: str) -> None:
        """Write parquet data to storage.

        Args:
            bucket: Where to store the data
            key: The file name of the stored data
            df: The data to store
            time_col: Name of the time column in df
        """
        exceptions_to_catch = [FileNotFoundError]
        if isinstance(self.storage, S3StorageClient):
            exceptions_to_catch.extend([self.storage.client.exceptions.NoSuchKey, ClientError])

        try:
            existing_bytes = self.storage.get_bytes(bucket, key)
            existing_df = pl.read_parquet(existing_bytes)
            combined_df = merge_dataframes(existing_df, df, time_col)
            logger.debug(f"Merging existing and new data for {bucket}/{key}")
        except tuple(exceptions_to_catch):
            combined_df = df
            logger.debug(f"No existing parquet at {bucket}/{key}; writing new file")

        buffer = BytesIO()
        combined_df.write_parquet(buffer)
        buffer.seek(0)
        self.storage.put_bytes(bucket, key, buffer.getvalue())
        logger.info(f"Wrote parquet to: {bucket}/{key}")
