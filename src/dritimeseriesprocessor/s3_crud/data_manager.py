"""Module for managing s3 CRUD operations"""

import logging
from datetime import date, datetime
from typing import List, Optional, Union

import polars as pl

from dritimeseriesprocessor.s3_crud.read import DuckDbParquetReader, ParquetReaderInterface
from dritimeseriesprocessor.utils import steralize_dates

logger = logging.getLogger(__name__)


def query_by_date_range(
    bucket_name: str,
    prefix: str,
    start_date: Union[date, datetime],
    end_date: Union[date, datetime, None],
    site_ids: List[str],
    columns: Optional[List[str]] = None,
    reader: ParquetReaderInterface = DuckDbParquetReader(),
) -> pl.DataFrame:
    """Reads Parquet files from an S3 bucket for a given date range and combines them into a single Polars DataFrame.

    Args:
        bucket_name: The name of the S3 bucket.
        prefix: The bucket prefix to search within.
        start_date: The start date of date range.
        end_date: The end date of date range.
        site_ids: list of site IDs to select.
        columns: Optional list of columns to select.
        reader: The object to use for reading the data. Assumed to be a DuckDbParquetReader by default.
    Returns:
        A Polars DataFrame containing the combined data from the Parquet files.
    """

    start_date, end_date = steralize_dates(start_date, end_date)

    columns_sql = ", ".join(columns) if columns else "*"
    site_ids_sql = f"AND site IN ({','.join(['?'] * len(site_ids))})" if site_ids else ""

    query = f"""
        SELECT {columns_sql}
        FROM read_parquet('s3://{bucket_name}/{prefix}/site=*/date=*/data.parquet')
        WHERE date BETWEEN ? AND ?
        {site_ids_sql}
    """

    params = [start_date, end_date, *site_ids]

    df = reader.read(query, params)

    return df
