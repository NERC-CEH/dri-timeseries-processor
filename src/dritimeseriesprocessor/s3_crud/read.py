"""Module for reading parquet data from S3 buckets"""

import logging
import os
from typing import List, Optional

import boto3
import duckdb
import polars as pl
from botocore.exceptions import ClientError

from dritimeseriesprocessor.configuration import app_config
from dritimeseriesprocessor.utils import remove_protocol_from_url

logger = logging.getLogger(__name__)

# localstack endpoint_url config required if running locally
if app_config.time_series_environment == "local":
    s3_client = boto3.client("s3", endpoint_url=app_config.endpoint_url, region_name=app_config.AWS_DEFAULT_REGION)
else:
    s3_client = boto3.client("s3", region_name=app_config.AWS_DEFAULT_REGION)


def read_parquet_by_query(query: str, params: Optional[List] = None) -> pl.DataFrame:
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
    logger.info("HELLO")
    logger.info(f"query: {query}")
    logger.info(f"Params: {params}")
    # Install httpfs to get support for object storage using the S3 API
    # https://duckdb.org/docs/extensions/httpfs/overview.html
    conn.execute(f"""
        INSTALL httpfs;
        LOAD httpfs;
        SET s3_region='{os.environ["AWS_DEFAULT_REGION"]}';
        SET s3_url_style='path';  -- required to get the endpoint url to build correctly in duckdb
    """)

    if app_config.time_series_environment == "local":
        logger.info("BLOCK RAN")
        # If running locally with localstack, need to explicitly set the endpoint URL and access key secrets.
        # Note that duckdb doesn't like the endpoint url to have http / https, so have to remove.
        endpoint_url = remove_protocol_from_url(app_config.endpoint_url)
        conn.execute(f"""
            SET s3_endpoint='{endpoint_url}';
            SET s3_use_ssl=false;     -- only required for localhost as it doesn't use https
            SET s3_access_key_id='{os.environ["AWS_ACCESS_KEY_ID"]}';
            SET s3_secret_access_key='{os.environ["AWS_SECRET_ACCESS_KEY"]}';
        """)

    try:
        df = conn.execute(query, params).pl()
        logger.info(conn.execute(query, params))
        return df
    except duckdb.HTTPException as e:
        logger.error(f"Failed to find data from query: {query}")
        raise e
    except duckdb.InvalidInputException as e:
        logger.error(f"Corrupt data found from query: {query}")
        raise e


def read_parquet_by_key(bucket_name: str, s3_key: str) -> pl.DataFrame:
    """Retrieves and loads a parquet object from an S3 bucket.

    Args:
        bucket_name: The name of the S3 bucket.
        s3_key: The key (path) of the object within the bucket.

    Returns:
        A Polars DataFrame containing the data from the Parquet file.

    Raises:
        (RuntimeError, ClientError): If there's any error in finding objects
        pl.exceptions.ComputeError: If corrupt data found in an object

    """
    try:
        data = s3_client.get_object(Bucket=bucket_name, Key=s3_key)
        contents = data["Body"].read()
        return pl.read_parquet(contents)
    except (RuntimeError, ClientError) as e:
        logger.error(f"Failed to get {s3_key} from {bucket_name}")
        raise e
    except pl.exceptions.ComputeError as e:
        logger.error(f"Corrupt data found in {s3_key} from {bucket_name}")
        raise e
