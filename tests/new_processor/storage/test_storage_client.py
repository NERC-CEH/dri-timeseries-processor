from typing import Iterator

import pytest

from new_processor.storage.storage_client import S3StorageClient

LOCALSTACK_ENDPOINT_URL = "http://localhost:4566"
LOCALSTACK_REGION = "eu-west-2"
LOCALSTACK_TEST_BUCKET = "test-bucket"


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
        storage_client.clear_bucket(LOCALSTACK_TEST_BUCKET)
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
        result = storage_client_with_files.get_bytes(LOCALSTACK_TEST_BUCKET, file_name)
        assert result == file_data

    def test_put_bytes(self, storage_client: S3StorageClient) -> None:
        file_name = "file.txt"
        file_data = b"data"
        storage_client.put_bytes(LOCALSTACK_TEST_BUCKET, file_name, file_data)
        result = storage_client.get_bytes(LOCALSTACK_TEST_BUCKET, file_name)
        assert result == file_data

    def test_list_keys(self, storage_client_with_files: S3StorageClient) -> None:
        result = storage_client_with_files.list_keys(LOCALSTACK_TEST_BUCKET)
        expected = ["file1.txt", "dir/file2.txt", "dir/nested/file3.txt"]
        assert sorted(result) == sorted(expected)

    def test_list_keys_empty_bucket(self, storage_client: S3StorageClient) -> None:
        result = storage_client.list_keys(LOCALSTACK_TEST_BUCKET)
        assert result == []

    @pytest.mark.parametrize("file_name", ["file1.txt", "dir/file2.txt", "dir/nested/file3.txt"])
    def test_delete_key(self, file_name: str, storage_client_with_files: S3StorageClient) -> None:
        # check the key exists to start with
        storage_client_with_files.get_bytes(LOCALSTACK_TEST_BUCKET, file_name)

        # delete the key
        storage_client_with_files.delete_key(LOCALSTACK_TEST_BUCKET, file_name)

        # now the key shouldn't exist
        with pytest.raises(storage_client_with_files.client.exceptions.NoSuchKey):
            storage_client_with_files.get_bytes(LOCALSTACK_TEST_BUCKET, file_name)

    def test_clear_bucket(self, storage_client_with_files: S3StorageClient) -> None:
        # check we have the 3 initial files
        initial = storage_client_with_files.list_keys(LOCALSTACK_TEST_BUCKET)
        assert len(initial) == 3

        storage_client_with_files.clear_bucket(LOCALSTACK_TEST_BUCKET)
        result = storage_client_with_files.list_keys(LOCALSTACK_TEST_BUCKET)
        # now should have 0 files
        assert result == []
