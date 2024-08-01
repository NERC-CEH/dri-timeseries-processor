"""Module for reading parquet data from S3 buckets"""

import datetime
import logging
import os
from typing import Any, Dict

import boto3
import polars as pl
from botocore.exceptions import ClientError

from dritimeseriesprocessor.configuration import app_config

logger = logging.getLogger(__name__)


# localstack endpoint_url config required if running locally
if "time_series_environment" not in os.environ:
    s3_client = boto3.client("s3", endpoint_url=app_config.endpoint_url, region_name=app_config.AWS_DEFAULT_REGION)
else:
    s3_client = boto3.client("s3", region_name=app_config.AWS_DEFAULT_REGION)


def read_parquet_by_config(bucket_name: str, filter_config: Dict[str, Any]) -> pl.DataFrame:
    """Reads Parquet files from an S3 bucket using config.

    Dataframes read by type and start/end date. Returned dataframes
    combined into one.

    Args:
        bucket_name: The name of the S3 bucket.
        filter_config: Filter parameters (as json).

    Returns:
        pl.DataFrame: A Polars DataFrame.
    """
    # Initialise empty Dataframe to load data into
    df = pl.DataFrame()

    for dataset in filter_config["datasets"]:
        dataset_type = dataset["type"]
        start_date = dataset["range"][0]
        end_date = dataset["range"][1]

        # Extract columns to filter
        columns = None
        if "columns" in dataset:
            columns = dataset["columns"]

        start_date = datetime.datetime.strptime(start_date, "%Y-%M-%d").date()
        end_date = datetime.datetime.strptime(end_date, "%Y-%M-%d").date()

        # Generate list of dates in the specified range
        date_list = pl.date_range(start_date, end_date, eager=True)

        for day in date_list:
            # Build s3 key for datasets
            year_month_day = f"{day.strftime('%Y-%m-%d')}.parquet"
            year_month = f"{day.strftime('%Y-%m')}"

            s3_key = f"{dataset_type}/{year_month}/{year_month_day}"

            # Load and append dataset
            try:
                current_df = read_parquet_object(bucket_name, s3_key, columns)
            except (RuntimeError, ClientError):
                logger.warning(f"Data not found for date: {day}")
            else:
                df = pl.concat([df, current_df], how="diagonal")

    return df


def read_parquet_object(bucket_name: str, s3_key: str, columns: list) -> pl.DataFrame:
    """Retrieves and loads a parquet object from an S3 bucket.

    Args:
        bucket_name: The name of the S3 bucket.
        s3_key: The key (path) of the object within the bucket.
        columns: Columns to filter on.

    Returns:
        pl.DataFrame: A Polars DataFrame containing the data from the Parquet file.

    Raises:
        Exception: If there's any error in retrieving or parsing the object.
    """
    try:
        data = s3_client.get_object(Bucket=bucket_name, Key=s3_key)
        contents = data["Body"].read()
        return pl.read_parquet(contents, columns=columns)
    except (RuntimeError, ClientError) as e:
        logger.error(f"Failed to get {s3_key} from {bucket_name}")
        raise e
