from pathlib import Path
from typing import Iterator

import pytest

from dritimeseriesprocessor.storage.storage_client import S3StorageClient

LOCALSTACK_ENDPOINT_URL = "http://localhost:4566"
LOCALSTACK_REGION = "eu-west-2"
LOCALSTACK_TEST_BUCKET = "test-bucket"
BUCKET_URL = f"s3://{LOCALSTACK_TEST_BUCKET}"


class TestSplitAccessUrl:
    @pytest.mark.parametrize(
        "url, expected",
        [
            (
                "s3://bucket/network=X/site=Y/date=2026-01-26/data.parquet",
                ("bucket", "network=X/site=Y/date=2026-01-26/data.parquet"),
            ),
            ("s3://bucket/network=X/site=Y/", ("bucket", "network=X/site=Y/")),
            ("s3://bucket/network=X/site=Y/date=2026-01", ("bucket", "network=X/site=Y/date=2026-01")),
            ("s3://bucket", ("bucket", "")),
            ("s3://bucket/", ("bucket", "")),
        ],
    )
    def test_splits_url_into_bucket_and_key(self, url: str, expected: tuple[str, str]) -> None:
        """Tests that an s3:// URL is split into its bucket and the rest of the path as the key."""
        assert S3StorageClient._split_access_url(url) == expected

    @pytest.mark.parametrize("url", ["bucket/key", "https://bucket/key", "/local/path/data.parquet"])
    def test_raises_for_non_s3_url(self, url: str) -> None:
        """Tests that a URL that doesn't start with s3:// is rejected."""
        with pytest.raises(ValueError, match="Expected an s3:// URL"):
            S3StorageClient._split_access_url(url)

    @pytest.mark.parametrize("url", ["s3://", "s3:///key"])
    def test_raises_when_url_has_no_bucket(self, url: str) -> None:
        """Tests that an s3:// URL with no bucket name is rejected."""
        with pytest.raises(ValueError, match="No bucket in URL"):
            S3StorageClient._split_access_url(url)


class TestS3StorageClient:
    @pytest.fixture
    def storage_client(self) -> Iterator[S3StorageClient]:
        # setup
        storage_client = S3StorageClient("test", "test", LOCALSTACK_REGION, endpoint_url=LOCALSTACK_ENDPOINT_URL)
        storage_client.client.create_bucket(
            Bucket=LOCALSTACK_TEST_BUCKET, CreateBucketConfiguration={"LocationConstraint": LOCALSTACK_REGION}
        )

        yield storage_client

        # teardown
        storage_client.delete_all(BUCKET_URL)
        storage_client.client.delete_bucket(Bucket=LOCALSTACK_TEST_BUCKET)

    @pytest.fixture
    def storage_client_with_files(self, storage_client: S3StorageClient) -> Iterator[S3StorageClient]:
        storage_client.client.put_object(Bucket=LOCALSTACK_TEST_BUCKET, Key="file1.txt", Body=b"file1")
        storage_client.client.put_object(Bucket=LOCALSTACK_TEST_BUCKET, Key="dir/file2.txt", Body=b"file2")
        storage_client.client.put_object(Bucket=LOCALSTACK_TEST_BUCKET, Key="dir/nested/file3.txt", Body=b"file3")
        yield storage_client

    @pytest.mark.parametrize(
        "file_name, file_data",
        [
            ("file1.txt", b"file1"),
            ("dir/file2.txt", b"file2"),
            ("dir/nested/file3.txt", b"file3"),
        ],
    )
    def test_get_bytes(self, file_name: str, file_data: str, storage_client_with_files: S3StorageClient) -> None:
        """Tests that a file's contents are read back from its URL."""
        result = storage_client_with_files.get_bytes(f"{BUCKET_URL}/{file_name}")
        assert result == file_data

    def test_put_bytes(self, storage_client: S3StorageClient) -> None:
        """Tests that bytes written to a URL can be read back from the same URL."""
        url = f"{BUCKET_URL}/file.txt"
        storage_client.put_bytes(url, b"data")
        assert storage_client.get_bytes(url) == b"data"

    def test_list_urls_with_prefix(self, storage_client_with_files: S3StorageClient) -> None:
        """Tests that only files under the prefix are listed, as full URLs."""
        result = storage_client_with_files.list_urls(f"{BUCKET_URL}/dir/")
        assert sorted(result) == [f"{BUCKET_URL}/dir/file2.txt", f"{BUCKET_URL}/dir/nested/file3.txt"]

    def test_list_urls_with_partial_name_prefix(self, storage_client_with_files: S3StorageClient) -> None:
        """Tests that the prefix can end part way through a name, as used for `date=YYYY-MM` listings."""
        result = storage_client_with_files.list_urls(f"{BUCKET_URL}/fi")
        assert result == [f"{BUCKET_URL}/file1.txt"]

    def test_list_urls_for_whole_bucket(self, storage_client_with_files: S3StorageClient) -> None:
        """Tests that a bucket-only URL lists every file in the bucket."""
        result = storage_client_with_files.list_urls(BUCKET_URL)
        assert sorted(result) == [
            f"{BUCKET_URL}/dir/file2.txt",
            f"{BUCKET_URL}/dir/nested/file3.txt",
            f"{BUCKET_URL}/file1.txt",
        ]

    def test_list_urls_when_nothing_matches(self, storage_client_with_files: S3StorageClient) -> None:
        """Tests that an empty list is returned when no file starts with the prefix."""
        assert storage_client_with_files.list_urls(f"{BUCKET_URL}/missing/") == []

    @pytest.mark.parametrize("file_name", ["file1.txt", "dir/file2.txt", "dir/nested/file3.txt"])
    def test_delete(self, file_name: str, storage_client_with_files: S3StorageClient) -> None:
        """Tests that a file deleted by URL can no longer be read."""
        url = f"{BUCKET_URL}/{file_name}"
        # check the file exists to start with
        storage_client_with_files.get_bytes(url)

        storage_client_with_files.delete(url)

        with pytest.raises(storage_client_with_files.client.exceptions.NoSuchKey):
            storage_client_with_files.get_bytes(url)

    def test_delete_all_for_whole_bucket(self, storage_client_with_files: S3StorageClient) -> None:
        """Tests that deleting everything under a bucket-only URL empties the bucket."""
        assert len(storage_client_with_files.list_urls(BUCKET_URL)) == 3

        storage_client_with_files.delete_all(BUCKET_URL)

        assert storage_client_with_files.list_urls(BUCKET_URL) == []

    def test_delete_all_only_removes_files_under_prefix(self, storage_client_with_files: S3StorageClient) -> None:
        """Tests that deleting everything under a prefix leaves files outside it alone."""
        storage_client_with_files.delete_all(f"{BUCKET_URL}/dir/")

        assert storage_client_with_files.list_urls(BUCKET_URL) == [f"{BUCKET_URL}/file1.txt"]

    def test_upload_file(self, tmp_path: Path, storage_client: S3StorageClient) -> None:
        """Tests that a local file uploaded to a URL can be read back from that URL."""
        local_file = tmp_path / "upload.txt"
        local_file.write_bytes(b"uploaded")
        url = f"{BUCKET_URL}/uploaded/upload.txt"

        storage_client.upload_file(url, local_file)

        assert storage_client.get_bytes(url) == b"uploaded"

    def test_download_file(self, tmp_path: Path, storage_client_with_files: S3StorageClient) -> None:
        """Tests that a file is downloaded from its URL to a local path, creating missing folders."""
        local_path = tmp_path / "downloads" / "file2.txt"

        storage_client_with_files.download_file(f"{BUCKET_URL}/dir/file2.txt", local_path)

        assert local_path.read_bytes() == b"file2"
