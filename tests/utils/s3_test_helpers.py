import io
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterator

import polars as pl
from tests.utils.fixture_helpers import TEST_DATA_INPUT_DIR
from tests.utils.metadata_helpers import E2E_INPUT_BUCKET, E2E_OUTPUT_BUCKET

from dritimeseriesprocessor.configuration.app_config import app_config
from dritimeseriesprocessor.storage.storage_client import S3StorageClient


@contextmanager
def get_s3_storage_client() -> Iterator[S3StorageClient]:
    cfg = app_config()
    storage_client = S3StorageClient("test", "test", cfg.AWS_DEFAULT_REGION, endpoint_url=cfg.endpoint_url)

    try:
        # Clean up in case of prior interrupted runs.
        remove_test_s3_bucket(E2E_INPUT_BUCKET, storage_client)
        remove_test_s3_bucket(E2E_OUTPUT_BUCKET, storage_client)
    except Exception:
        pass

    create_test_s3_bucket(E2E_INPUT_BUCKET, storage_client, cfg.AWS_DEFAULT_REGION)
    create_test_s3_bucket(E2E_OUTPUT_BUCKET, storage_client, cfg.AWS_DEFAULT_REGION)

    upload_folder_to_s3(storage_client, E2E_INPUT_BUCKET, TEST_DATA_INPUT_DIR / "end_to_end")
    upload_folder_to_s3(storage_client, E2E_INPUT_BUCKET, TEST_DATA_INPUT_DIR / "partitioned")

    try:
        yield storage_client
    finally:
        # teardown
        remove_test_s3_bucket(E2E_INPUT_BUCKET, storage_client)
        remove_test_s3_bucket(E2E_OUTPUT_BUCKET, storage_client)


def remove_test_s3_bucket(bucket: str, storage_client: S3StorageClient) -> None:
    """Clear and delete a test S3 bucket.

    Args:
        bucket: Bucket name to remove.
        storage_client: S3 client wrapper used for bucket operations.
    """
    storage_client.clear_bucket(bucket)
    storage_client.client.delete_bucket(Bucket=bucket)


def create_test_s3_bucket(bucket: str, storage_client: S3StorageClient, default_region: str) -> None:
    """Create a test S3 bucket.

    Args:
        bucket: Bucket name to create.
        storage_client: S3 client wrapper used for bucket operations.
    """
    storage_client.client.create_bucket(
        Bucket=bucket,
        CreateBucketConfiguration={"LocationConstraint": default_region},
    )


def upload_folder_to_s3(storage_client: S3StorageClient, bucket: str, folder: Path) -> None:
    """Upload all Parquet files beneath a folder to a bucket.

    The object key is computed as the file path relative to ``folder``.

    Args:
        storage_client: S3 client wrapper used for uploads.
        bucket: Destination bucket.
        folder: Root folder containing Parquet files to upload.
    """
    for file in folder.rglob("*.parquet"):
        key = str(file.relative_to(folder))
        storage_client.put_bytes(bucket, key, file.read_bytes())


def create_hourly_test_data(
    start: datetime,
    end: datetime,
    bucket_name: str,
    upload: bool = False,
    storage_client: S3StorageClient | None = None,
) -> pl.DataFrame:
    frames = []

    for day in (start + timedelta(d) for d in range((end - start).days + 1)):
        for site in ["site1", "site2"]:
            data = {
                "time": [day + timedelta(hours=i) for i in range(24)] * 2,
                "SITE_ID": [site] * 48,
                "col1": list(range(48)),
                "col2": list(range(48, 96)),
            }
            df = pl.DataFrame(data)
            frames.append(df)

            if upload:
                if not storage_client:
                    raise RuntimeError("S3 storage client required for upload of test data.")

                buf = io.BytesIO()
                df.write_parquet(buf)

                key = f"cosmos/dataset=test_dataset/site={site}/date={day.strftime('%Y-%m-%d')}/data.parquet"
                storage_client.put_bytes(bucket_name, key, buf.getvalue())

    return pl.concat(frames)
