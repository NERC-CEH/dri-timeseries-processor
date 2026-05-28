import io
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterator

import polars as pl
from tests.utils.fixture_helpers import PARQUET_DATA_INPUT_DIR, PARQUET_DATA_PROCESSED_DIR, TEST_DATA_INPUT_DIR
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

    upload_folder_to_s3(storage_client, E2E_INPUT_BUCKET, PARQUET_DATA_INPUT_DIR)
    upload_folder_to_s3(storage_client, E2E_INPUT_BUCKET, TEST_DATA_INPUT_DIR / "partitioned")
    # Pre-processed data from external systems (e.g. NMDB) lives in the same real S3
    # bucket as our processor's outputs. Upload it to the output bucket so it can be
    # resolved as a load-only dependency during tests.
    upload_folder_to_s3(storage_client, E2E_OUTPUT_BUCKET, PARQUET_DATA_PROCESSED_DIR)

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
        CreateBucketConfiguration={"LocationConstraint": default_region},  # type: ignore[arg-type]
    )


def upload_folder_to_s3(
    storage_client: S3StorageClient, bucket: str, folder: Path, key_base: Path | None = None
) -> None:
    """Upload all Parquet files beneath a folder to a bucket.

    The object key is computed as the file path relative to ``key_base`` (defaults to ``folder``).
    Supplying a ``key_base`` that is a parent of ``folder`` preserves the intermediate path
    segments in the S3 key, which is useful when uploading a subfolder while keeping the
    network-level prefix (e.g. ``nmdb/``) in the key.

    Args:
        storage_client: S3 client wrapper used for uploads.
        bucket: Destination bucket.
        folder: Root folder containing Parquet files to upload.
        key_base: Base path used to compute the S3 key. Defaults to ``folder``.
    """
    key_base = key_base or folder
    for file in folder.rglob("*.parquet"):
        key = str(file.relative_to(key_base))
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
