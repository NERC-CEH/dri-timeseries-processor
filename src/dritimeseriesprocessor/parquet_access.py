"""Module for accessing parquet data from S3 buckets"""

import logging
import os
from datetime import date

import boto3
import polars as pl
from botocore.exceptions import ClientError

from dritimeseriesprocessor.configuration import app_config

logger = logging.getLogger(__name__)

# endpoint_url config required if running locally
if "ingestion_environment" not in os.environ:
    S3_CLIENT = boto3.client("s3", endpoint_url=app_config.endpoint_url)
else:
    S3_CLIENT = boto3.client("s3")


def get_parquet_by_dates(bucket_name: str, start_date: date, end_date: date) -> pl.DataFrame:
    """Reads Parquet files from an S3 bucket for a given date range and combines them into a single Polars DataFrame.

    Args:
        bucket_name (str): The name of the S3 bucket.
        start_date (date): The start date of date range.
        end_date (date): The end date of date range.

    Returns:
        pl.DataFrame: A Polars DataFrame containing the combined data from the Parquet files.
    """
    # Generate list of dates in range
    if start_date > end_date:
        raise UserWarning(f"Start date must come before end date: {start_date} > {end_date}")
    date_list = pl.date_range(start_date, end_date, eager=True)

    # Initialise empty Dataframe to load data into
    df = pl.DataFrame()

    # Get parquet file for each date and join them together
    for dt in date_list:
        s3_key = f"{dt.strftime('%Y-%m-%d')}.parquet"

        try:
            dt_df = get_parquet_object(bucket_name, s3_key)
        except (RuntimeError, ClientError):
            logger.warning(f"Data not found for date: {dt}")
        else:
            df = pl.concat([df, dt_df])

    return df


def get_parquet_object(bucket_name: str, s3_key: str) -> pl.DataFrame:
    """Retrieves and loads a parquet object from an S3 bucket.

    Args:
        bucket_name (str): The name of the S3 bucket.
        s3_key (str): The key (path) of the object within the bucket.

    Returns:
        pl.DataFrame: A Polars DataFrame containing the data from the Parquet file.

    Raises:
        Exception: If there's any error in retrieving or parsing the object.
    """
    try:
        data = S3_CLIENT.get_object(Bucket=bucket_name, Key=s3_key)
        contents = data["Body"].read()
        return pl.read_parquet(contents)
    except (RuntimeError, ClientError) as e:
        logger.error(f"Failed to get {s3_key} from {bucket_name}")
        raise e
