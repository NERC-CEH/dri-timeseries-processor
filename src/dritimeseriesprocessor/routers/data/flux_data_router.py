import logging
from datetime import date
from pathlib import Path

from dritimeseriesprocessor.storage.storage_client import StorageClient

logger = logging.getLogger(__name__)


class FluxDataRouter:
    """Routes flux data files between S3 and the local filesystem.

    Unlike the DuckDB-based DataRouter for timeseries, this works with raw files:
    downloading them from S3 for EddyPro to process, and uploading EddyPro output
    files back to S3.
    """

    def __init__(self, storage_client: StorageClient) -> None:
        self._storage = storage_client

    def download_raw_files(
        self,
        bucket: str,
        network: str,
        dataset: str,
        site: str,
        start_date: date,
        end_date: date,
        local_dir: Path,
    ) -> Path:
        """Download raw .dat files for a site within the date range.

        S3 layout: {network}/dataset={dataset}/site={site}/date=YYYY-MM-DD/<files>

        Filters keys by date partition. Downloads to local_dir preserving only the
        filename (not the S3 directory structure).

        Returns local_dir.
        """
        prefix = f"{network}/dataset={dataset}/site={site}/"
        all_keys = self._storage.list_keys_with_prefix(bucket, prefix)
        local_dir.mkdir(parents=True, exist_ok=True)

        count = 0
        for key in all_keys:
            # Extract the date from the partition: .../date=2024-08-14/...
            key_date = self._extract_date_from_key(key)
            if key_date and start_date <= key_date <= end_date:
                filename = key.rsplit("/", 1)[-1]
                local_path = local_dir / filename
                self._storage.download_file(bucket, key, local_path)
                count += 1

        logger.info("Downloaded %d raw files for site %s", count, site)
        return local_dir

    def download_biomet(self, bucket: str, network: str, site: str, local_dir: Path) -> Path | None:
        """Download biomet CSV file(s) for a site.

        S3 layout: {network}/ancillary/biomet/site={site}/

        Returns path to first downloaded file, or None if nothing found.
        """
        prefix = f"{network}/ancillary/biomet/site={site}/"
        keys = self._storage.list_keys_with_prefix(bucket, prefix)
        if not keys:
            logger.info("No biomet files found for site %s", site)
            return None

        local_dir.mkdir(parents=True, exist_ok=True)
        for key in keys:
            filename = key.rsplit("/", 1)[-1]
            local_path = local_dir / filename
            self._storage.download_file(bucket, key, local_path)

        first_file = local_dir / keys[0].rsplit("/", 1)[-1]
        logger.info("Downloaded %d biomet files for site %s", len(keys), site)
        return first_file

    def download_dynamic_metadata(self, bucket: str, network: str, site: str, local_dir: Path) -> Path | None:
        """Download dynamic metadata .txt file for a site.

        S3 layout: {network}/ancillary/dynamic_metadata/site={site}/

        Returns path to downloaded file, or None if nothing found.
        """
        prefix = f"{network}/ancillary/dynamic_metadata/site={site}/"
        keys = self._storage.list_keys_with_prefix(bucket, prefix)
        if not keys:
            logger.info("No dynamic metadata files found for site %s", site)
            return None

        local_dir.mkdir(parents=True, exist_ok=True)
        filename = keys[0].rsplit("/", 1)[-1]
        local_path = local_dir / filename
        self._storage.download_file(bucket, keys[0], local_path)
        logger.info("Downloaded dynamic metadata for site %s", site)
        return local_path

    def upload_output_directory(
        self,
        bucket: str,
        local_output_dir: Path,
        network: str,
        dataset: str,
        site: str,
        run_date: str,
    ) -> int:
        """Upload all files from a local directory to S3.

        Walks local_output_dir recursively. For each file builds S3 key:
          {network}/dataset={dataset}/site={site}/date={run_date}/{relative_path}

        Returns count of files uploaded.
        """
        count = 0
        for local_file in local_output_dir.rglob("*"):
            if not local_file.is_file():
                continue
            relative = local_file.relative_to(local_output_dir)
            s3_key = f"{network}/dataset={dataset}/site={site}/date={run_date}/{relative}"
            self._storage.upload_file(bucket, s3_key, local_file)
            logger.debug("Uploaded %s", s3_key)
            count += 1

        logger.info(
            "Uploaded %d files to s3://%s/%s/dataset=%s/site=%s/date=%s/",
            count,
            bucket,
            network,
            dataset,
            site,
            run_date,
        )
        return count

    @staticmethod
    def _extract_date_from_key(key: str) -> date | None:
        """Extract date from a hive partition key like .../date=2024-08-14/..."""
        for part in key.split("/"):
            if part.startswith("date="):
                try:
                    return date.fromisoformat(part[5:])
                except ValueError:
                    return None
        return None
