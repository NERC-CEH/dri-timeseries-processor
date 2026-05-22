"""
Data routing interfaces for retrieving time series data.
"""

import logging
import tempfile
from abc import ABC, abstractmethod
from datetime import date, datetime, timedelta
from pathlib import Path

import polars as pl

from dritimeseriesprocessor.io_backend.reader import DuckDBParquetReader, RawFileReader
from dritimeseriesprocessor.models.domain_models.time_series_container import (
    TimeSeriesContainer,
    check_common_attributes,
)

logger = logging.getLogger(__name__)


class DataRouter(ABC):
    """Abstract interface for loading a dataset's data from storage.

    Implementations resolve a dataset's storage location from its metadata and either return its data as a
    Polars DataFrame (`query_by_date_range`) or stage its raw files into a local directory (`stage_locally`).
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

    @abstractmethod
    def stage_locally(self, container: TimeSeriesContainer, start_date: datetime, end_date: datetime) -> Path:
        """Download a dataset's raw files for the date range into a local directory.

        Args:
            container: Container whose metadata locates the raw files in storage.
            start_date: Start of the date range (inclusive).
            end_date: End of the date range (inclusive).

        Returns:
            Path to the local directory containing the downloaded files.
        """
        pass

    @abstractmethod
    def query_history_columns(
        self,
        bucket: str,
        network: str,
        resolution: str,
        site: str,
        time_col: str,
        columns: list[str],
        start_date: date,
        end_date: date,
    ) -> pl.DataFrame:
        """Load named columns from the processed hive partition for a date range.

        Args:
            bucket: S3 bucket containing the processed parquet files.
            network: Network identifier (top-level hive partition key).
            resolution: ISO-8601 resolution string (e.g. "PT30M").
            site: Site identifier used in the hive partition.
            time_col: Name of the timestamp column in the parquet files.
            columns: Column names to select (in addition to time_col).
            start_date: Start of the date range (inclusive).
            end_date: End of the date range (inclusive).

        Returns:
            DataFrame with time_col and the requested columns.
        """
        pass

    @abstractmethod
    def cleanup(self) -> None:
        """Release any local resources (e.g. staged temp directories) held by the router."""
        pass


class S3DataRouter(DataRouter):
    """Routes dataset loads to S3-backed storage.

    Parquet datasets are queried via a `DuckDBParquetReader`; raw file datasets are staged locally via a
    `RawFileReader`. Both share the same S3 hive-partition layout.
    """

    def __init__(self, reader: DuckDBParquetReader, raw_reader: RawFileReader):
        self.reader = reader
        self._raw_reader = raw_reader
        self._staged: list[tempfile.TemporaryDirectory] = []

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
        network, site_id, resolution, bucket, source_dataset, time_column_name = check_common_attributes(
            list(containers),
            ["network", "source_site_identifier", "resolution", "source_bucket", "source_dataset", "time_column_name"],
        )

        # Ensure columns with hyphens can be parsed by SQL
        columns = ", ".join([f'"{c.source_column}"' for c in containers])

        # ToDo: partitions will be consolidated into a single partition. See FPM-998.
        if "PROCESSED" in source_dataset:
            base = self._site_partition_prefix(network, "resolution", resolution, site_id)
        else:
            base = self._site_partition_prefix(network, "dataset", source_dataset, site_id)

        bucket_path = f"s3://{bucket}/{base}/**/date=*/data.parquet"
        query = f"""
            SELECT {time_column_name}, {columns}
            FROM read_parquet(
                '{bucket_path}', hive_partitioning=true
            )
            WHERE
                (date BETWEEN ? AND ?);
        """
        return self.reader.read(query, [start_date, end_date])

    def stage_locally(self, container: TimeSeriesContainer, start_date: datetime, end_date: datetime) -> Path:
        """Download a container's raw files for the date range into a new temp directory.

        Args:
            container: Container whose metadata locates the raw files in storage.
            start_date: Start of the date range (inclusive).
            end_date: End of the date range (inclusive).

        Returns:
            Path to the local directory containing the downloaded files.
        """
        tmp = tempfile.TemporaryDirectory(prefix=f"raw_{container.source_site_identifier}_")
        self._staged.append(tmp)
        local_dir = Path(tmp.name)

        current = start_date.date()
        last = end_date.date()
        total_downloaded = 0
        while current <= last:
            prefix = f"{container.s3_dataset_path}/date={current.isoformat()}/"
            logger.info("Downloading raw files from s3://%s/%s", container.s3_bucket, prefix)
            downloaded = self._raw_reader.download(
                container.s3_bucket,  # type: ignore[arg-type]
                prefix,
                local_dir,
            )
            total_downloaded += len(downloaded)
            current += timedelta(days=1)

        logger.info("Staged %d raw file(s) for %s into %s", total_downloaded, container.ts_id, local_dir)
        return local_dir

    def query_history_columns(
        self,
        bucket: str,
        network: str,
        resolution: str,
        site: str,
        time_col: str,
        columns: list[str],
        start_date: date,
        end_date: date,
    ) -> pl.DataFrame:
        """Load named columns from the processed hive partition for a date range.

        Args:
            bucket: S3 bucket containing the processed parquet files.
            network: Network identifier (top-level hive partition key).
            resolution: ISO-8601 resolution string (e.g. "PT30M").
            site: Site identifier used in the hive partition.
            time_col: Name of the timestamp column in the parquet files.
            columns: Column names to select (in addition to time_col).
            start_date: Start of the date range (inclusive).
            end_date: End of the date range (inclusive).

        Returns:
            DataFrame with time_col and the requested columns.
        """
        col_sql = ", ".join([f'"{c}"' for c in columns])
        base = self._site_partition_prefix(network, "resolution", resolution, site)
        bucket_path = f"s3://{bucket}/{base}/**/date=*/data.parquet"
        query = f"""
            SELECT "{time_col}", {col_sql}
            FROM read_parquet(
                '{bucket_path}', hive_partitioning=true
            )
            WHERE
                (date BETWEEN ? AND ?);
        """
        return self.reader.read(query, [start_date, end_date])

    def cleanup(self) -> None:
        """Clean up all temporary directories created for staging."""
        for tmp in self._staged:
            try:
                tmp.cleanup()
            except Exception:
                logger.exception("Failed to clean up temporary directory.")
        self._staged.clear()

    @staticmethod
    def _site_partition_prefix(network: str, partition_key: str, partition_value: str, site: str) -> str:
        """Build the leading `network/<key>=<value>/site=<site>` hive-partition segments."""
        return f"{network}/{partition_key}={partition_value}/site={site}"
