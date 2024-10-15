"""Module for managing s3 CRUD operations"""

import logging
from datetime import date, datetime
from typing import List, Optional, Union

import polars as pl
import time

from dritimeseriesprocessor.s3_crud.read import DuckDbParquetReader, ParquetReaderInterface
from dritimeseriesprocessor.utils import steralize_dates, steralize_site_ids, month_list, year_list

logger = logging.getLogger(__name__)


def query_by_date_range(
    bucket_name: str,
    prefix: str,
    start_date: Union[date, datetime],
    end_date: Union[date, datetime, None],
    columns: Optional[List[str]] = None,
    site_ids: Optional[Union[str, List[str]]] = None,
    date_field: str = "time",
    site_id_field: str = "SITE_ID",
    reader: ParquetReaderInterface = DuckDbParquetReader(),
) -> pl.DataFrame:
    """Reads Parquet files from an S3 bucket for a given date range and combines them into a single Polars DataFrame.

    Args:
        bucket_name: The name of the S3 bucket.
        prefix: The bucket prefix to search within.
        start_date: The start date of date range.
        end_date: The end date of date range.
        columns: Optional list of columns to select.
        site_ids: Optional list of site IDs (or single site ID) to select.
        date_field: The name of the field that we query date on. Defaults to time.
        site_id_field: The name of the field that we query site ID on. Defaults to SITE_ID.
        reader: The object to use for reading the data. Assumed to be a DuckDbParquetReader by default.
    Returns:
        A Polars DataFrame containing the combined data from the Parquet files.
    """

    start_date, end_date = steralize_dates(start_date, end_date)
    site_ids = steralize_site_ids(site_ids)

    columns_sql = ", ".join(columns) if columns else "*"
    site_ids_sql = f"AND {site_id_field} IN ({','.join(['?'] * len(site_ids))})" if site_ids else ""

    print(start_date)
    print(end_date)
    years = year_list(start_date, end_date)
    months = month_list(start_date, end_date)
    print(years)
    print(months)

    query = f"""
        EXPLAIN ANALYZE
        SELECT {columns_sql}
        FROM read_parquet('s3://{bucket_name}/{prefix}/*/*.parquet', hive_partitioning=true, hive_types = {{date: DATE}})
        WHERE date BETWEEN ? AND ?
        {site_ids_sql}
    """
    print(query)
    params = [start_date, end_date, *site_ids]

    times = []
    #for i in range(0,10):
    #    start = time.time()
    df = reader.read(query, params)
    #    end = time.time()
    #    times.append(end-start)
    
    print(sum(times)/ 10)

    print(df)
    return df
