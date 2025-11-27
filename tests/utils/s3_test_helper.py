import io
from datetime import datetime, timedelta
from pathlib import Path

import pytest

import polars as pl
from polars.testing import assert_frame_equal

from new_processor.configuration.app_config import app_config
from new_processor.storage.storage_client import S3StorageClient


@pytest.fixture
def s3_storage_client() -> S3StorageClient:
    cfg = app_config()
    client = S3StorageClient(cfg.endpoint_url)
    return client


def assert_bucket_matches(s3_storage_client: S3StorageClient, expected_base: Path, bucket: str) -> None:
    expected_keys = [
        p.relative_to(expected_base).as_posix()
        for p in expected_base.rglob("data.parquet")
    ]
    actual_keys = sorted(s3_storage_client.list_keys(bucket))
    assert actual_keys == sorted(expected_keys), "Mismatch in S3 keys"

    for key in expected_keys:
        expected_df = pl.read_parquet(expected_base / key)
        actual_df = pl.read_parquet(io.BytesIO(s3_storage_client.get_bytes(bucket, key)))
        assert_frame_equal(expected_df, actual_df, check_dtypes=False)


def create_hourly_test_data(
        start: datetime, end: datetime, upload: bool = False, storage_client: S3StorageClient | None = None
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
                bucket_name = "ukceh-fdri-staging-timeseries-level-0"
                storage_client.put_bytes(bucket_name, key, buf.getvalue())

    return pl.concat(frames)
