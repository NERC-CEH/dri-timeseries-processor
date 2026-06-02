"""Module for reading data from storage."""

import logging
from abc import ABC, abstractmethod
from pathlib import Path

import duckdb
import polars as pl
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_fixed

from dritimeseriesprocessor.io_backend.duckdb_connection import DuckDBConnectionFactory
from dritimeseriesprocessor.storage.storage_client import StorageClient

logger = logging.getLogger(__name__)


class ParquetReaderInterface(ABC):
    """Interface for defining parquet reading objects"""

    @abstractmethod
    def read(self, *args, **kwargs) -> pl.DataFrame:
        """Abstract method for read operations"""
        pass


class DuckDBParquetReader(ParquetReaderInterface):
    """DuckDB implementation of the parquet reader.

    DuckDB is configured via an injected DuckDBConnectionFactory, which encapsulates all environment-specific
    behaviour (local / staging / production).
    """

    def __init__(self, connection_factory: DuckDBConnectionFactory) -> None:
        """Initialize the DuckDBParquetReader.

        Args:
            connection_factory: Object responsible for creating correctly configured DuckDB connections.
        """
        self._connection_factory = connection_factory

    @retry(
        retry=retry_if_exception_type(duckdb.InvalidInputException),
        wait=wait_fixed(2),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    def read(self, query: str, params: list | None = None) -> pl.DataFrame:
        """Uses DuckDb to read parquet files using a prepared SQL query.

        Args:
            query: SQL query string.
            params: Optional list of parameters for the prepared SQL statement

        Returns:
            A Polars DataFrame of query results.

        Raises:
            duckdb.HTTPException: If there's any error in finding objects
            duckdb.InvalidInputException: If corrupt data found in an object
        """
        conn = self._connection_factory.create()

        try:
            df = conn.execute(query, params).pl()
            return df

        except duckdb.HTTPException:
            logger.error(f"Parquet read failed due to invalid file.\nQuery: {query}")
            raise

        except duckdb.InvalidInputException:
            logger.error(f"Parquet file contained corrupt data.\nQuery: {query}")
            raise

        except duckdb.IOException:
            # No parquet file found, so return an empty dataframe
            return pl.DataFrame()

        finally:
            conn.close()


class RawFileReader:
    """Downloads raw files from storage to a local directory.

    A thin counterpart to `DuckDBParquetReader`: it executes a prepared download
    (a bucket and prefix) just as the parquet reader executes a prepared query.
    Building prefixes from dataset metadata and managing the destination directory
    are the router's responsibility.
    """

    def __init__(self, storage: StorageClient) -> None:
        self._storage = storage

    def download(self, bucket: str, prefix: str, local_dir: Path) -> list[Path]:
        """Download every object under `prefix` in `bucket` into `local_dir`.

        Args:
            bucket: Storage bucket to read from.
            prefix: Key prefix identifying the objects to download.
            local_dir: Local directory to download the objects into.

        Returns:
            The local paths of the downloaded files.
        """
        keys = self._storage.list_keys_with_prefix(bucket, prefix)
        if not keys:
            logger.warning("No raw files found under s3://%s/%s", bucket, prefix)
            return []

        downloaded: list[Path] = []
        for key in keys:
            local_path = local_dir / key.rsplit("/", 1)[-1]
            self._storage.download_file(bucket, key, local_path)
            downloaded.append(local_path)
            logger.debug("Downloaded: %s -> %s", key, local_path)

        return downloaded
