"""
Data routing interfaces for retrieving time series data.
"""

from abc import ABC, abstractmethod
from datetime import datetime

import polars as pl

from new_processor.io_backend.reader import DuckDBParquetReader
from new_processor.models.domain_models.time_series_container import TimeSeriesContainer


class DataRouter(ABC):
    """Abstract interface for loading time series data.

    Implementations are responsible for retrieving data for a given dataset and time window, and returning it as a
    Polars DataFrame.
    """

    @abstractmethod
    def query_by_date_range(
        self, container: TimeSeriesContainer, start_date: datetime, end_date: datetime
    ) -> pl.DataFrame:
        """Retrieve data for specified date range.

        Args:
            container: Contains metadata required for building the dataset query.
            start_date: Start of the date range (inclusive).
            end_date: End of the date range (inclusive).

        Returns:
            A Polars DataFrame containing the data.
        """
        pass


class DuckDBDataRouter(DataRouter):
    def __init__(self, reader: DuckDBParquetReader):
        self.reader = reader

    def query_by_date_range(
        self, container: TimeSeriesContainer, start_date: datetime, end_date: datetime
    ) -> pl.DataFrame:
        """Retrieve data for data range using DuckDB SQL query.

        Args:
            container: Contains metadata required for building the dataset query.
            start_date: Start of the date range (inclusive).
            end_date: End of the date range (inclusive).

        Returns:
            A Polars DataFrame containing the data.
        """

        # TODO: Time column should not be hard coded. Where in metadata is best?
        # TODO: Bucket path (network=.../dataset=...) is specific to COSMOS raw bucket.  How to make this generic?
        # TODO: Network is not a partition on the RAW bucket, but is on the PROCESSED bucket - reconcile?
        # TODO: Site ID in metadata is different (e.g. cosmos-bunny vs. BUNNY)

        site_hack = container.source_site.split("-")[1].upper()

        partitions = [
            f"{container.network}",
            f"dataset={container.source_dataset}",
            "site=*",
            "date=*",
        ]
        partitions_str = "/".join(partitions)
        bucket_path = f"s3://{container.source_bucket}/{partitions_str}/data.parquet"
        query = f"""
            SELECT time, {container.source_column}
            FROM read_parquet('{bucket_path}')
            WHERE
                (date BETWEEN ? AND ?) AND
                site = ?;
        """
        params = [start_date, end_date, site_hack]
        return self.reader.read(query, params)
