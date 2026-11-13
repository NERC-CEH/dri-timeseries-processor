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
    behaviour (local / staging / production). One connection is made on the first query and reused for the rest,
    so its setup and HTTPS connections aren't repeated.
    """

    def __init__(self, connection_factory: DuckDBConnectionFactory) -> None:
        """Initialize the DuckDBParquetReader.

        Args:
            connection_factory: Object responsible for creating correctly configured DuckDB connections.
        """
        self._connection_factory = connection_factory
        self._connection: duckdb.DuckDBPyConnection | None = None

    def _get_connection(self) -> duckdb.DuckDBPyConnection:
        """Return the shared connection, making it on first use."""
        if self._connection is None:
            self._connection = self._connection_factory.create()
        return self._connection

    def close(self) -> None:
        """Close the shared connection, if there is one."""
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    @retry(
        retry=retry_if_exception_type(duckdb.InvalidInputException),
        wait=wait_fixed(2),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    def read(self, query: str, params: list | None = None) -> pl.DataFrame:  # type: ignore[override]
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
        conn = self._get_connection()

        try:
            df = conn.sql(query, params=params).pl()
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


class RawFileReader:
    """Downloads raw files from storage to a local directory.

    A thin counterpart to `DuckDBParquetReader`: it executes a prepared download (a URL prefix) just as the parquet
    reader executes a prepared query.

    Getting the URL prefix from dataset metadata and managing the destination directory are the router's responsibility.
    """

    def __init__(self, storage: StorageClient) -> None:
        self._storage = storage

    def download(self, prefix_url: str, local_dir: Path) -> list[Path]:
        """Download every file whose URL starts with `prefix_url` into `local_dir`.

        Args:
            prefix_url: The start of the URLs to download, e.g. `s3://bucket/.../site=X/date=2026-01-20/`.
            local_dir: Local directory to download the files into.

        Returns:
            The local paths of the downloaded files.
        """
        urls = self._storage.list_urls(prefix_url)
        if not urls:
            logger.warning("No raw files found under %s", prefix_url)
            return []

        downloaded: list[Path] = []
        for url in urls:
            local_path = local_dir / url.rsplit("/", 1)[-1]
            self._storage.download_file(url, local_path)
            downloaded.append(local_path)
            logger.debug("Downloaded: %s -> %s", url, local_path)

        return downloaded
