"""
Data routing interfaces for retrieving time series data.
"""

from abc import ABC, abstractmethod
from datetime import datetime

import polars as pl

from dritimeseriesprocessor.io_backend.reader import DuckDBParquetReader
from dritimeseriesprocessor.models.domain_models.time_series_container import (
    TimeSeriesContainer,
    check_common_attributes,
)


class DataRouter(ABC):
    """Abstract interface for loading time series data.

    Implementations are responsible for retrieving data for a given dataset and time window, and returning it as a
    Polars DataFrame.
    """

    @abstractmethod
    def query_by_date_range(
        self, *containers: TimeSeriesContainer, start_date: datetime, end_date: datetime
    ) -> pl.DataFrame:
        """Retrieve data for specified date range.

        Args:
            containers: One or more containers with metadata required for building the dataset query.
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
        self, *containers: TimeSeriesContainer, start_date: datetime, end_date: datetime
    ) -> pl.DataFrame:
        """Retrieve data for data range using DuckDB SQL query.

        Args:
            containers: One or more containers with metadata required for building the dataset query.
            start_date: Start of the date range (inclusive).
            end_date: End of the date range (inclusive).

        Returns:
            A Polars DataFrame containing the data.
        """
        network, site_id, resolution, bucket, source_dataset, time_column_name = check_common_attributes(  # type: ignore[misc]
            list(containers),
            ["network", "source_site_identifier", "resolution", "source_bucket", "source_dataset", "time_column_name"],
        )

        # Ensure columns with hyphens can be parsed by SQL
        columns = ", ".join([f'"{c.source_column}"' for c in containers])

        # ToDo: partitions will be consolidated into a single partition. See FPM-998.
        partitions_raw = [
            f"{network}",
            f"dataset={source_dataset}",
            f"site={site_id}",
            "**",
            "date=*",
        ]

        partitions_processed = [
            f"{network}",
            f"resolution={resolution}",
            f"site={site_id}",
            "**",
            "date=*",
        ]

        partition = partitions_raw
        if "PROCESSED" in source_dataset:
            partition = partitions_processed

        partitions_str = "/".join(partition)
        bucket_path = f"s3://{bucket}/{partitions_str}/data.parquet"
        query = f"""
            SELECT {time_column_name}, {columns}
            FROM read_parquet(
                '{bucket_path}', hive_partitioning=true
            )
            WHERE
                (date BETWEEN ? AND ?);
        """
        return self.reader.read(query, [start_date, end_date])
