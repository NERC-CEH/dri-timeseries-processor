"""Module for managing s3 CRUD operations"""

import logging
from datetime import date, datetime
from typing import List, Optional, Tuple, Union

import polars as pl

from dritimeseriesprocessor.s3_crud.read import read_parquet_by_query

logger = logging.getLogger(__name__)


def read_by_date_range(
    bucket_name: str,
    data_category: str,
    start_date: Union[date, datetime],
    end_date: Union[date, datetime],
    columns: Optional[List[str]] = None,
    site_ids: Optional[Union[str, List[str]]] = None,
    date_field: str = "time",
    site_id_field: str = "SITE_ID",
) -> pl.DataFrame:
    """Reads Parquet files from an S3 bucket for a given date range and combines them into a single Polars DataFrame.

    Args:
        bucket_name: The name of the S3 bucket.
        data_category: The data category to select.
        start_date: The start date of date range.
        end_date: The end date of date range.
        columns: Optional list of columns to select.
        site_ids: Optional list of site IDs (or single site ID) to select.
        date_field: The name of the field that we query date on.
        site_id_field: The name of the field that we query site ID on.

    Returns:
        A Polars DataFrame containing the combined data from the Parquet files.
    """
    start_date, end_date = configure_dates(start_date, end_date)
    site_ids = configure_site_ids(site_ids)

    columns_sql = ", ".join(columns) if columns else "*"
    site_ids_sql = f"AND {site_id_field} IN ({','.join(['?'] * len(site_ids))})" if site_ids else ""

    query = f"""
        SELECT {columns_sql}
        FROM read_parquet('s3://{bucket_name}/*{data_category}*/**/*.parquet')
        WHERE {date_field} >= ?
          AND {date_field} <= ?
          {site_ids_sql}
    """
    params = [start_date, end_date, *site_ids]

    df = read_parquet_by_query(query, params)
    return df


def configure_dates(
    start_date: Union[date, datetime], end_date: Optional[Union[date, datetime]] = None
) -> Tuple[Union[date, datetime], datetime]:
    """
    Configures and validates start and end dates.

    Args:
        start_date: The start date.
        end_date: The end date. If None, defaults to start_date.

    Returns:
        A tuple containing the start date and the end date.

    Raises:
        UserWarning: If the start date is after the end date.
    """
    # If end_date is not provided, set it to start_date
    if end_date is None:
        end_date = start_date

    # Ensure the start_date is not after the end_date
    if start_date > end_date:
        raise UserWarning(f"Start date must come before end date: {start_date} > {end_date}")

    # If start_date is of type date, convert it to datetime with time at start of the day
    if isinstance(start_date, date) and not isinstance(start_date, datetime):
        start_date = datetime.combine(start_date, datetime.min.time())

    # If end_date is of type date, convert it to datetime to include the entire day
    if isinstance(end_date, date) and not isinstance(end_date, datetime):
        end_date = datetime.combine(end_date, datetime.max.time())

    return start_date, end_date


def configure_site_ids(site_ids: Optional[Union[str, List[str]]] = None) -> List[str]:
    """
    Configures site IDs into a list format.

    Args:
        site_ids: A single site ID as a string or a list of site IDs.
            If None, defaults to an empty list.

    Returns:
        A list of site IDs.
    """
    if site_ids is None or site_ids == "":
        # If no site IDs are provided, return an empty list
        site_ids = []
    elif isinstance(site_ids, str):
        # If a single site ID string is provided, convert it to a list
        site_ids = [site_ids]

    return site_ids
