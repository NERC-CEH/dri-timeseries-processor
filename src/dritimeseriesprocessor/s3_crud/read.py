"""Module for reading parquet data from S3 buckets"""

import logging
import os
from abc import ABC, abstractmethod
from typing import List, Optional

import boto3
import duckdb
import polars as pl
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_fixed

from dritimeseriesprocessor.configuration import app_config
from dritimeseriesprocessor.utils import remove_protocol_from_url

logger = logging.getLogger(__name__)


class ParquetReaderInterface(ABC):
    """Interface for defining parquet reading objects"""

    @abstractmethod
    def read(self, *args, **kwargs) -> pl.DataFrame:
        """Abstract method for read operations"""


class DuckDbParquetReader(ParquetReaderInterface):
    """DuckDB implementation of the parquet reader"""

    @retry(
        retry=retry_if_exception_type(duckdb.InvalidInputException),
        wait=wait_fixed(2),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    def read(self, query: str, params: Optional[List] = None) -> pl.DataFrame:
        """Uses DuckDb to read parquet files from an S3 bucket using a prepared SQL query.

        Args:
            query: SQL query string.
            params: Optional list of parameters for the prepared SQL statement

        Returns:
            A Polars DataFrame of query results.

        Raises:
            duckdb.HTTPException: If there's any error in finding objects
            duckdb.InvalidInputException: If corrupt data found in an object
        """
        conn = duckdb.connect()
        # Install httpfs to get support for object storage using the S3 API
        # https://duckdb.org/docs/extensions/httpfs/overview.html
        # Create secret for S3 authentication
        # force_download - fixes the "missing magic bytes at end of file" error
        # by forcing upfront download of the file before processing
        conn.execute("""
            INSTALL httpfs;
            LOAD httpfs;
            SET force_download = true;
        """)

        if app_config.environment == "local":
            # If running locally with localstack, need to explicitly set the endpoint URL and access key secrets.
            # Note that duckdb doesn't like the endpoint url to have http / https, so have to remove.
            logger.debug("Configured DuckDB for local environment.")
            endpoint_url = remove_protocol_from_url(app_config.endpoint_url)
            conn.execute(f"""
                SET s3_endpoint='{endpoint_url}';
                SET s3_url_style='path';  -- required to get the endpoint url to build correctly in duckdb
                SET s3_use_ssl=false;     -- only required for localhost as it doesn't use https
                SET s3_access_key_id='{os.environ["AWS_ACCESS_KEY_ID"]}';
                SET s3_secret_access_key='{os.environ["AWS_SECRET_ACCESS_KEY"]}';
            """)

        if app_config.environment in ["staging", "production"]:
            logger.debug("Configured DuckDB for production environment.")

            sess = boto3.Session()
            credentials = sess.get_credentials().get_frozen_credentials()

            conn.execute(f"""
                CREATE SECRET aws_secret (
                        TYPE S3,
                        KEY_ID '{credentials.access_key}',
                        SECRET '{credentials.secret_key}',
                        SESSION_TOKEN '{credentials.token}',
                        REGION '{sess.region_name}'
                );
            """)

        if app_config.environment == "staging-fake":
            logger.debug("Configured DuckDB for fake staging.")

        try:
            df = conn.execute(query, params).pl()
            logger.info(query)
            return df
        except duckdb.HTTPException as e:
            logger.error(f"Failed to find data from query: {query}")
            raise e
        except duckdb.InvalidInputException as e:
            logger.error(f"Corrupt data found from query: {query}")
            raise e
