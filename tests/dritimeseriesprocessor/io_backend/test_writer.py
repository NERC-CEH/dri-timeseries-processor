import io
from typing import Iterator, cast
from unittest.mock import MagicMock

import polars as pl
import pytest
from polars.testing import assert_frame_equal

from dritimeseriesprocessor.configuration.app_config import app_config
from dritimeseriesprocessor.io_backend.writer import ByteParquetWriter
from dritimeseriesprocessor.storage.storage_client import S3StorageClient


class NoSuchKey(Exception):
    pass


mock_s3 = MagicMock()
mock_s3.exceptions = MagicMock()
mock_s3.exceptions.NoSuchKey = NoSuchKey


class FakeNoSuchKey(Exception):
    # Define a fake NoSuchKey exception class
    pass


class TestByteParquetWriter:
    """Simple tests that check the core functionality of the class"""

    @pytest.mark.parametrize("err_type", [FileNotFoundError, FakeNoSuchKey])
    def test_write_new_file(self, err_type: Exception, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that no file found writes only the new data"""
        if err_type is FakeNoSuchKey:
            mock_storage = MagicMock(spec=S3StorageClient)
            mock_storage.client = MagicMock()
            mock_storage.client.exceptions.NoSuchKey = FakeNoSuchKey
        else:
            mock_storage = MagicMock()

        writer = ByteParquetWriter(storage=mock_storage)

        df = pl.DataFrame({"t": [1], "value": [10]})

        mock_storage.get_bytes.side_effect = err_type
        # Patch the merge dataframes method so we can verify it wasn't called
        mock_merge_dataframes = MagicMock()
        monkeypatch.setattr("dritimeseriesprocessor.io_backend.writer.merge_dataframes", mock_merge_dataframes)

        writer.write("bucket", "file.parquet", df, time_col="t")

        # Verify merge dataframes wasn't called
        mock_merge_dataframes.assert_not_called()

        # Verify written parquet is valid and contains df
        bucket, key, data = mock_storage.put_bytes.call_args.args
        out_df = pl.read_parquet(data)
        assert out_df.equals(df)

    def test_write_merge_with_existing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that file found writes the new data merged with the previous data"""
        mock_storage_client = MagicMock()
        writer = ByteParquetWriter(storage=mock_storage_client)

        existing_df = pl.DataFrame({"t": [1], "value": [10]})
        new_df = pl.DataFrame({"t": [2], "value": [20]})

        # Mock the return of the bytes containing the existing dataframe
        buf = io.BytesIO()
        existing_df.write_parquet(buf)
        buf.seek(0)
        mock_storage_client.get_bytes.return_value = buf.read()

        # Patch the merge dataframes method so we can verify it was called
        merged = pl.DataFrame({"t": [1, 2], "value": [10, 20]})
        mock_merge_dataframes = MagicMock(return_value=merged)
        monkeypatch.setattr("dritimeseriesprocessor.io_backend.writer.merge_dataframes", mock_merge_dataframes)

        writer.write("bucket", "file.parquet", new_df, time_col="t")

        # Verify merge dataframes was called
        mock_merge_dataframes.assert_called_once()

        # Verify written parquet is valid and contains df
        bucket, key, data = mock_storage_client.put_bytes.call_args.args
        out_df = pl.read_parquet(data)
        assert_frame_equal(out_df, merged)


BUCKET_NAME = "ukceh-dri-staging-ingested"


@pytest.fixture
def s3_storage_client() -> S3StorageClient:
    cfg = app_config()
    client = S3StorageClient(
        cast(str, cfg.AWS_ACCESS_KEY_ID),
        cast(str, cfg.AWS_SECRET_ACCESS_KEY),
        cast(str, cfg.AWS_DEFAULT_REGION),
        cfg.endpoint_url,
    )
    return client


@pytest.fixture
def setup_test_data(s3_storage_client: S3StorageClient) -> Iterator:
    # setup
    s3_storage_client.clear_bucket(BUCKET_NAME)
    yield
    # teardown
    s3_storage_client.clear_bucket(BUCKET_NAME)


@pytest.fixture
def writer(s3_storage_client: S3StorageClient) -> ByteParquetWriter:
    return ByteParquetWriter(storage=s3_storage_client)


@pytest.mark.usefixtures("setup_test_data")
class TestByteParquetWriterIntegration:
    """Integration tests that check specific usages of the class"""

    def test_write_new_file(self, writer: ByteParquetWriter, s3_storage_client: S3StorageClient) -> None:
        df = pl.DataFrame({"t": [1], "value": [10]})

        writer.write(BUCKET_NAME, "data.parquet", df, time_col="t")

        out_bytes = s3_storage_client.get_bytes(BUCKET_NAME, "data.parquet")
        result = pl.read_parquet(out_bytes)

        assert_frame_equal(result, df)

    def test_write_merge_existing(self, writer: ByteParquetWriter, s3_storage_client: S3StorageClient) -> None:
        df1 = pl.DataFrame({"t": [1], "value": [10]})
        df2 = pl.DataFrame({"t": [2], "value": [20]})

        writer.write(BUCKET_NAME, "merged.parquet", df1, time_col="t")
        writer.write(BUCKET_NAME, "merged.parquet", df2, time_col="t")

        out_bytes = s3_storage_client.get_bytes(BUCKET_NAME, "merged.parquet")
        result = pl.read_parquet(out_bytes)
        expected = pl.DataFrame({"t": [1, 2], "value": [10, 20]})

        assert_frame_equal(result, expected)

    @pytest.mark.parametrize(
        "df1, df2, expected",
        [
            (
                pl.DataFrame({"t": [1], "value": [10]}),
                pl.DataFrame({"t": [2], "value": [20], "extra_col": [30]}),
                pl.DataFrame({"t": [1, 2], "value": [10, 20], "extra_col": [None, 30]}),
            ),
            (
                pl.DataFrame({"t": [1], "value": [10]}),
                pl.DataFrame({"t": [2], "extra_col": [30]}),
                pl.DataFrame({"t": [1, 2], "value": [10, None], "extra_col": [None, 30]}),
            ),
        ],
    )
    def test_write_merge_existing_diff_cols(
        self,
        df1: pl.DataFrame,
        df2: pl.DataFrame,
        expected: pl.DataFrame,
        writer: ByteParquetWriter,
        s3_storage_client: S3StorageClient,
    ) -> None:
        writer.write(BUCKET_NAME, "merged.parquet", df1, time_col="t")
        writer.write(BUCKET_NAME, "merged.parquet", df2, time_col="t")

        out_bytes = s3_storage_client.get_bytes(BUCKET_NAME, "merged.parquet")
        result = pl.read_parquet(out_bytes)

        assert_frame_equal(result, expected, check_column_order=False)

    def test_write_merge_different_time_cols(
        self, writer: ByteParquetWriter, s3_storage_client: S3StorageClient
    ) -> None:
        df1 = pl.DataFrame({"t": [1], "value": [10]})
        df2 = pl.DataFrame({"time": [2], "value": [20]})

        writer.write(BUCKET_NAME, "merged.parquet", df1, time_col="t")

        with pytest.raises(ValueError):
            writer.write(BUCKET_NAME, "merged.parquet", df2, time_col="time")

        out_bytes = s3_storage_client.get_bytes(BUCKET_NAME, "merged.parquet")
        result = pl.read_parquet(out_bytes)
        assert_frame_equal(result, df1)

    def test_overwrite_same_timestamp(self, writer: ByteParquetWriter, s3_storage_client: S3StorageClient) -> None:
        """Ensures merge overwrites duplicate timestamps correctly."""
        df1 = pl.DataFrame({"t": [1], "value": [10]})
        df2 = pl.DataFrame({"t": [1], "value": [999]})

        writer.write(BUCKET_NAME, "dupes.parquet", df1, time_col="t")
        writer.write(BUCKET_NAME, "dupes.parquet", df2, time_col="t")

        out_bytes = s3_storage_client.get_bytes(BUCKET_NAME, "dupes.parquet")
        result = pl.read_parquet(out_bytes)
        expected = pl.DataFrame({"t": [1], "value": [999]})

        assert_frame_equal(result, expected)
