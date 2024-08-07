""" Module for managing s3 CRUD operations
"""
from datetime import date
import logging
from typing import List, Optional

import polars as pl

from read import read_parquet_by_query

logger = logging.getLogger(__name__)


def read_by_date_range(bucket_name: str, data_category: str, start_date: date, end_date: date,
                       columns: Optional[List[str]] = None, date_field: str = 'time') -> pl.DataFrame:
    """ Reads Parquet files from an S3 bucket for a given date range and combines them into a single Polars DataFrame.

    Args:
        bucket_name: The name of the S3 bucket.
        data_category: The data category to select.
        start_date: The start date of date range.
        end_date: The end date of date range.
        columns: Optional list of columns to select.
        date_field: The name of the field that we query date on.

    Returns:
        pl.DataFrame: A Polars DataFrame containing the combined data from the Parquet files.
    """
    if start_date > end_date:
        raise UserWarning(f"Start date must come before end date: {start_date} > {end_date}")

    columns_sql = ", ".join(columns) if columns else "*"
    query = f"""
        SELECT {columns_sql} 
        FROM read_parquet('s3://{bucket_name}/*{data_category}*/**/*.parquet')
        WHERE {date_field} >= ? AND {date_field} <= ?;
    """
    params = [start_date, end_date]

    df = read_parquet_by_query(query, params)
    return df


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    START_DATE = date(2024, 1, 17)
    END_DATE = date(2024, 1, 19)

    from dritimeseriesprocessor.configuration import app_config

    DF = read_by_date_range(app_config.level_0_bucket,
                       'PRECIP_1MIN',
                       START_DATE,
                       END_DATE,
                       ['time', 'SITE_ID', 'P_STATUS'])
    print(DF)
