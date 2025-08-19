"""Module for handling data writing logic"""

import logging
from abc import ABC, abstractmethod
from collections import defaultdict
from datetime import datetime
from io import BytesIO
from typing import List, Tuple

import polars as pl
from botocore.client import BaseClient
from botocore.exceptions import ClientError
from mypy_boto3_s3.client import S3Client
from polars.dataframe import DataFrame

from dritimeseriesprocessor.metrics_exporter import metrics
from dritimeseriesprocessor.typing import TimeseriesContainerWithDerivations

logger = logging.getLogger(__name__)


class WriterInterface(ABC):
    """Interface for defining parquet writing objects"""

    @abstractmethod
    def write(self, *args, **kwargs) -> None:
        """Abstract method for write operations"""


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

    @staticmethod
    def _build_s3_key(network: str, site_id: str, resolution: str, date: datetime) -> str:
        """Builds a S3 key.

        network=<network>/date=<date>site=<site_id>/resolution=<resolution>/data.parquet

        Args:
            network: The name of the network
            site_id: The site_id the data comes from
            resolution: The resoluion of the data
            date: The date the data comes from

        Returns:
            A string of the key
        """

        day = date.strftime("%Y-%m-%d")

        return f"network={network}/date={day}/site={site_id}/resolution={resolution}/data.parquet"

    @staticmethod
    def _split_by_date(df: pl.DataFrame) -> List[Tuple[datetime, DataFrame]]:
        """Split a dataframe by the date.

        Args:
            df: A polars dataframe

        Returns:
            dataframes split by date.
        """

        return [(group[0][0], group[1]) for group in df.group_by([pl.col("time").dt.date()])]

    @staticmethod
    def _group_data_by_resolution_and_site(
        processed_ts_ids: TimeseriesContainerWithDerivations,
    ) -> List[Tuple[str, str, pl.DataFrame]]:
        """Group the processed ts_ids by resolution and site and combine the timeseries objects.

        Args:
            processed_ts_ids: The time series ids that have been processed.

        Returns:
            The site, resolution and combined timestream objects
        """
        resolutions = defaultdict(list)

        for ts_metadata in processed_ts_ids:
            key = (ts_metadata["resolution"], ts_metadata["sourceSite"])
            data = ts_metadata["data"].df

            resolutions[key].append(data)

        # combine timestream objects
        # TODO replace with timestream method when developed
        return [(site_res[0], site_res[1], pl.concat(data, how="align")) for site_res, data in resolutions.items()]

    def structure(
        self, processed_timeseries: TimeseriesContainerWithDerivations, bucket_name: str, network: str
    ) -> List[List[List[Tuple[datetime, pl.DataFrame] | str]]]:
        """
        Structure the processed data ready for writing.

        First group the data by resolution and site, then split into days.

        Args:
            processed_timeseries: the timeseries that have been processed
            bucket_name: the name of bucket to write to
            network: the processing network

        Returns:
            Data and metadata required for asynchronous writing
        """
        grouped_ts_ids = self._group_data_by_resolution_and_site(processed_timeseries)

        data_to_write = []
        for data_object in grouped_ts_ids:
            resolution, site, data = data_object
            data_to_write.append([[data for data in self._split_by_date(data)], site, resolution, bucket_name, network])

        return data_to_write

    def _merge_dataframes(self, existing_df: pl.DataFrame, current_df: pl.DataFrame) -> pl.DataFrame:
        """
        Data to merge will always be the same resolution and date, but each dataframe could have different columns and/or timestamps"""


        # Do a full outer join to make sure we get all the timestamps
        # Coalesce any columns that exist in both
        # Make sure to keep columns from both dataframes
        common_columns = set(existing_df.columns) & set(current_df.columns)
        update_columns = {col for col in common_columns if col != "time"}
        extra_right_columns = set(current_df.columns) - common_columns
        extra_left_columns = set(existing_df.columns) - common_columns

        combined_df = (
            existing_df.join(current_df, on="time", how="full", suffix="_current", coalesce=True)
            .select(
                "time",
                *extra_left_columns,
                *[pl.coalesce(f"{col}_current", col).alias(col) for col in update_columns],
                *extra_right_columns
            )
        )

        print(combined_df)


    @metrics.track_s3_write_time()
    def write(
        self, data: List[Tuple[datetime, pl.DataFrame]], site_id: str, resolution: str, bucket_name: str, network: str
    ) -> None:
        """Uploads objects to an S3 bucket.

        This function attempts to upload objects to a specified S3 bucket
        using the provided S3 client. Objects are converted to bytes.
        If the upload fails, it logs an error message and re-raises the exception.

        Args:
            data: The data to write
            site_id: The ID of the site
            resolution: The resolution of the data
            bucket_name: The name of the S3 bucket.
            network: The name of the network

        Raises:
            RuntimeError, ClientError
        """

        for date, df in data:
            s3_key = self._build_s3_key(network, site_id, resolution, date)

            buffer = BytesIO()

            try:
                # Try to get the existing object
                existing_data = self.s3_client.get_object(Bucket=bucket_name, Key=s3_key)

                # If file exists, read it, append new data, and write back
                existing_df = pl.read_parquet(existing_data["Body"].read())
                combined_df = self._merge_dataframes(existing_df, df)
                combined_df.write_parquet(buffer)
            except Exception as e:
                if isinstance(e, ClientError) and e.response["Error"]["Code"] == "NoSuchKey":
                    logger.warning(f"Failed to get {s3_key} from {bucket_name}")
                    # If file doesn't exist, write new file
                    df.write_parquet(buffer)
                else:
                    logger.error(f"Unexpected error when writing to parquet: {e}")
                    logger.exception(e)

            buffer.seek(0)
            self.s3_client.put_object(Bucket=bucket_name, Key=s3_key, Body=buffer.getvalue())
            
            logger.info(f"Data for date {date} site {site_id} and resolution {resolution} written to s3://{bucket_name}/{s3_key}")
