"""
Factories for creating environment specific DuckDB connections.

Each factory implements the same interface and returns a configured DuckDB connection suitable for reading parquet files
from object storage via the S3 API.
"""

from abc import ABC, abstractmethod
from contextlib import contextmanager
from typing import Iterator

import boto3
import duckdb

from new_processor.configuration.app_config import app_config
from new_processor.utils.enums import Environment
from new_processor.utils.urls import remove_protocol_from_url


class DuckDBConnectionFactory(ABC):
    """Provides a configured DuckDB connection."""

    @abstractmethod
    def create(self) -> duckdb.DuckDBPyConnection:
        """Abstract method to create the connection"""

    @staticmethod
    def _configure_duckdb_base() -> duckdb.DuckDBPyConnection:
        """Apply core DuckDB configuration required for all environments."""
        conn = duckdb.connect()
        conn.execute("""
            INSTALL httpfs;
            LOAD httpfs;
            SET force_download=true;
        """)
        return conn


class LocalStackDuckDBConnectionFactory(DuckDBConnectionFactory):
    """Create DuckDB connections configured for LocalStack."""

    def __init__(self, endpoint_url: str, aws_access_key: str, aws_secret_key: str):
        """Initialize the local DuckDb connection.

        Args:
            endpoint_url: The LocalStack endpoint URL
            aws_access_key: Access key used by DuckDB to authenticate against LocalStack.
            aws_secret_key: Secret key used by DuckDB to authenticate against LocalStack.
        """
        self.endpoint_url = endpoint_url
        self.aws_access_key = aws_access_key
        self.aws_secret_key = aws_secret_key

    def create(self) -> duckdb.DuckDBPyConnection:
        """Return a DuckDB connection configured for LocalStack.

        Returns:
            An active DuckDB connection configured for reading from S3 using LocalStack.
        """
        conn = self._configure_duckdb_base()

        # If running locally with localstack, need to explicitly set the endpoint URL and access key secrets.
        # Note that duckdb doesn't like the endpoint url to have http / https, so have to remove.
        endpoint = remove_protocol_from_url(self.endpoint_url)
        conn.execute(f"""
            SET s3_endpoint='{endpoint}';
            SET s3_url_style='path';
            SET s3_use_ssl=false;
            SET s3_access_key_id='{self.aws_access_key}';
            SET s3_secret_access_key='{self.aws_secret_key}';
        """)

        return conn


class MinimalDuckDBConnectionFactory(DuckDBConnectionFactory):
    """Minimal DuckDB configuration for non-S3 test environments."""

    def create(self) -> duckdb.DuckDBPyConnection:
        """Return a DuckDB connection.

        Returns:
            An active DuckDB connection.
        """
        conn = self._configure_duckdb_base()
        return conn


class AwsDuckDBConnectionFactory(DuckDBConnectionFactory):
    """Create DuckDB connections configured for AWS."""

    def __init__(self, session: boto3.Session):
        """Initialize the local DuckDb connection.

        Args:
            session: The boto3 session to use for making connections.
        """
        self.session = session

    def create(self) -> duckdb.DuckDBPyConnection:
        """Return a DuckDB connection configured for AWS S3 access.

        Returns:
            An active DuckDB connection configured for reading from S3 on AWS.
        """
        conn = self._configure_duckdb_base()

        creds = self.session.get_credentials().get_frozen_credentials()
        conn.execute(f"""
            CREATE SECRET aws_secret (
                TYPE S3,
                KEY_ID '{creds.access_key}',
                SECRET '{creds.secret_key}',
                SESSION_TOKEN '{creds.token}',
                REGION '{self.session.region_name}'
            );
        """)
        return conn


def create_duckdb_factory() -> DuckDBConnectionFactory:
    """Create the appropriate DuckDBConnectionFactory for the current environment.

    Returns:
        A DuckDBConnectionFactory instance configured for the runtime environment.

    Raises:
        ValueError: If the environment is unrecognised.
    """
    cfg = app_config()

    if cfg.environment is Environment.LOCAL:
        return LocalStackDuckDBConnectionFactory(
            endpoint_url=cfg.endpoint_url,
            aws_access_key=cfg.AWS_ACCESS_KEY_ID,
            aws_secret_key=cfg.AWS_SECRET_ACCESS_KEY,
        )

    if cfg.environment in (Environment.STAGING, Environment.PRODUCTION):
        return AwsDuckDBConnectionFactory(boto3.Session())

    if cfg.environment is Environment.STAGING_FAKE:
        return MinimalDuckDBConnectionFactory()

    raise ValueError(f"Unsupported environment: {cfg.environment}")


@contextmanager
def duckdb_connection() -> Iterator[duckdb.DuckDBPyConnection]:
    factory = create_duckdb_factory()
    conn = factory.create()
    try:
        yield conn
    finally:
        conn.close()
