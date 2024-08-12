"""Module for managing s3 CRUD operations"""

import logging
from datetime import date, datetime
from typing import List, Optional, Union

import polars as pl

from dritimeseriesprocessor.s3_crud.read import read_parquet_by_query
from dritimeseriesprocessor.utils import steralize_dates, steralize_site_ids

logger = logging.getLogger(__name__)


def query_by_date_range(
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
        date_field: The name of the field that we query date on. Defaults to time.
        site_id_field: The name of the field that we query site ID on. Defaults to SITE_ID.

    Returns:
        A Polars DataFrame containing the combined data from the Parquet files.
    """
    start_date, end_date = steralize_dates(start_date, end_date)
    site_ids = steralize_site_ids(site_ids)

    columns_sql = ", ".join(columns) if columns else "*"
    site_ids_sql = f"AND {site_id_field} IN ({','.join(['?'] * len(site_ids))})" if site_ids else ""

    query = f"""
        SELECT {columns_sql}
        FROM read_parquet('s3://{bucket_name}/{data_category}/**/*.parquet')
        WHERE {date_field} >= ?
          AND {date_field} <= ?
          {site_ids_sql}
    """
    params = [start_date, end_date, *site_ids]

    df = read_parquet_by_query(query, params)
    return df
