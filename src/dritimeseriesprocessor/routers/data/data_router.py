"""
Data routing interfaces for retrieving time series data.
"""

import logging
import tempfile
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from pathlib import Path

import polars as pl

from dritimeseriesprocessor.io_backend.reader import DuckDBParquetReader, RawFileReader
from dritimeseriesprocessor.models.domain_models.time_series_container import (
    TimeSeriesContainer,
    check_common_attributes,
)
from dritimeseriesprocessor.storage.storage_client import StorageClient

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
    def cleanup(self) -> None:
        """Release any local resources (e.g. staged temp directories) held by the router."""
        pass


class S3DataRouter(DataRouter):
    """Routes dataset loads to S3-backed storage.

    Parquet datasets are queried via a `DuckDBParquetReader`; raw file datasets are staged locally via a
    `RawFileReader`. Both find a dataset's files under its access URL, in daily `date=YYYY-MM-DD` folders. The
    storage client lists which daily parquet files fall inside a date range, so DuckDB only opens those.
    """

    def __init__(self, reader: DuckDBParquetReader, raw_reader: RawFileReader, storage: StorageClient):
        self.reader = reader
        self._raw_reader = raw_reader
        self._storage = storage
        self._staged: list[tempfile.TemporaryDirectory] = []

    def query_by_date_range(
        self, *containers: TimeSeriesContainer, start_date: datetime, end_date: datetime
    ) -> pl.DataFrame:
        """Retrieve data for date range using DuckDB SQL query.

        The daily files inside the date range are listed first and DuckDB is given that exact list. Matching columns
        by name (`union_by_name`) handles files whose columns differ, and only costs a read of each listed file's
        schema rather than every file in the site's history.

        Args:
            containers: One or more containers with metadata required for building the dataset query.
            start_date: Start of the date range (inclusive).
            end_date: End of the date range (inclusive).

        Returns:
            A Polars DataFrame containing the data.
        """

        distribution_url, time_column_name = check_common_attributes(
            list(containers), ["distribution_url", "time_column_name"]
        )
        if not distribution_url:
            raise ValueError(f"No distribution access URL for datasets: {[c.ts_id for c in containers]}")

        # Select via COLUMNS(lambda) rather than naming columns directly: a source_column that doesn't exist in the
        # parquet files is then silently omitted from the result instead of failing the whole query, so the caller
        # can fail that one dataset without losing the rest of the group.
        requested_columns = ", ".join([f"'{c.source_column}'" for c in containers])

        file_urls = self._list_files(distribution_url, start_date, end_date)
        if not file_urls:
            logger.warning(f"No parquet files found under {distribution_url} between {start_date} and {end_date}")
            return pl.DataFrame()

        query = f"""
            SELECT {time_column_name}, COLUMNS(c -> c IN ({requested_columns}))
            FROM read_parquet(?, union_by_name=true);
        """
        return self.reader.read(query, [file_urls])

    def stage_locally(self, container: TimeSeriesContainer, start_date: datetime, end_date: datetime) -> Path:
        """Download a container's raw files for the date range into a new temp directory.

        Args:
            container: Container whose metadata locates the raw files in storage.
            start_date: Start of the date range (inclusive).
            end_date: End of the date range (inclusive).

        Returns:
            Path to the local directory containing the downloaded files.
        """
        if not container.distribution_url:
            raise ValueError(f"No distribution access URL for dataset: {container.ts_id}")

        tmp = tempfile.TemporaryDirectory(prefix=f"raw_{container.source_site_identifier}_")
        self._staged.append(tmp)
        local_dir = Path(tmp.name)

        current = start_date.date()
        last = end_date.date()
        total_downloaded = 0
        while current <= last:
            prefix_url = f"{container.distribution_url}/date={current.isoformat()}/"
            logger.info("Downloading raw files from %s", prefix_url)
            downloaded = self._raw_reader.download(prefix_url, local_dir)
            total_downloaded += len(downloaded)
            current += timedelta(days=1)

        logger.info("Staged %d raw file(s) for %s into %s", total_downloaded, container.ts_id, local_dir)
        return local_dir

    def cleanup(self) -> None:
        """Close the parquet reader's DuckDB connection and clean up all temporary directories created for staging."""
        self.reader.close()
        for tmp in self._staged:
            try:
                tmp.cleanup()
            except Exception:
                logger.exception("Failed to clean up temporary directory.")
        self._staged.clear()

    def _list_files(self, distribution_url: str, start_date: datetime, end_date: datetime) -> list[str]:
        """List the URLs of the dataset's `data.parquet` files from `start_date` to `end_date`, inclusive.

        Args:
            distribution_url: The dataset's access URL, e.g. `s3://bucket/network=X/collection=Y/site=Z`.
            start_date: First day to include.
            end_date: Last day to include.

        Returns:
            File URLs, one per day that has a file.
        """
        first_day = start_date.date()
        last_day = end_date.date()
        # One listing per month in the range, e.g. `date=2026-09` then `date=2026-10`
        months = pl.date_range(first_day.replace(day=1), last_day, "1mo", eager=True).dt.strftime("%Y-%m")

        file_urls = []
        date_prefix = f"{distribution_url}/date="
        for month in months:
            for file_url in self._storage.list_urls(f"{date_prefix}{month}"):
                day = file_url.removeprefix(date_prefix).split("/")[0]
                if first_day.isoformat() <= day <= last_day.isoformat() and file_url.endswith("/data.parquet"):
                    file_urls.append(file_url)
        return file_urls
