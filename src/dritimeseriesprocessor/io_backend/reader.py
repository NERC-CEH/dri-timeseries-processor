"""Module for reading parquet data"""

import logging
from abc import ABC, abstractmethod

import duckdb
import polars as pl
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_fixed

from dritimeseriesprocessor.io_backend.duckdb_connection import DuckDBConnectionFactory

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
    def read(self, query: str, params: list = None) -> pl.DataFrame:
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
            raise
            # return pl.DataFrame()
