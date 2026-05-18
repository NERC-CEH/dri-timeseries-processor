"""Raw flux file I/O for EddyPro runs.

Handles downloading raw .dat files from S3 for EddyPro input.

Bucket names are never stored on this class — they are passed per-operation
from the caller, who derives them from ``container.source_bucket`` (which
already comes from the Metadata API).
"""

import logging
from datetime import date, timedelta
from pathlib import Path

from dritimeseriesprocessor.storage.storage_client import StorageClient

logger = logging.getLogger(__name__)


class FluxS3Client:
    """Handles raw flux file download for EddyPro runs."""

    def __init__(self, storage_client: StorageClient) -> None:
        self._storage = storage_client

    def download_raw_dat_files(
        self,
        bucket: str,
        site: str,
        dataset: str,
        network: str,
        start_date: date,
        end_date: date,
        local_dir: Path,
    ) -> list[Path]:
        """Download all raw files for a site/date range from S3 into local_dir."""
        local_dir.mkdir(parents=True, exist_ok=True)
        downloaded: list[Path] = []

        current = start_date
        while current <= end_date:
            date_prefix = self._build_raw_date_prefix(
                network=network,
                dataset=dataset,
                site=site,
                data_date=current,
            )
            keys = self._storage.list_keys_with_prefix(bucket, date_prefix)
            if not keys:
                logger.debug("No raw files found for site %s under %s", site, date_prefix)
                current += timedelta(days=1)
                continue

            for key in keys:
                filename = key.rsplit("/", 1)[-1]
                local_path = local_dir / filename
                self._storage.download_file(bucket, key, local_path)
                downloaded.append(local_path)
                logger.debug("Downloaded: %s -> %s", key, local_path)

            current += timedelta(days=1)

        logger.info("Downloaded %d raw .dat files for site %s (bucket=%s)", len(downloaded), site, bucket)
        return downloaded

    @staticmethod
    def _build_raw_date_prefix(network: str, dataset: str, site: str, data_date: date) -> str:
        """Build the S3 prefix for raw flux files for a single date."""
        partitions = [
            network,
            f"dataset={dataset}",
            f"site={site}",
            f"date={data_date.isoformat()}",
        ]
        return "/".join(partitions) + "/"
