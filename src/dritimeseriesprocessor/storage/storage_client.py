from abc import ABC, abstractmethod
from pathlib import Path

import boto3


class StorageClient(ABC):
    """Abstract base class defining methods for retrieving and writing data."""

    @abstractmethod
    def get_bytes(self, url: str) -> bytes:
        """Retrieve data from the underlying storage.

        Args:
            url: Full URL of the file.

        Returns:
            The full contents of the data as a bytestring.
        """
        pass

    @abstractmethod
    def put_bytes(self, url: str, data: bytes) -> None:
        """Write data to the underlying storage.

        Args:
            url: Full URL of the file.
            data: The bytes to be written.
        """
        pass

    @abstractmethod
    def download_file(self, url: str, local_path: Path) -> None:
        """Download a single file from storage to a local file path.

        Args:
            url: Full URL of the file.
            local_path: Where to save the file locally.
        """
        pass

    @abstractmethod
    def upload_file(self, url: str, local_path: Path) -> None:
        """Upload a local file to storage.

        Args:
            url: Full URL to upload the file to.
            local_path: The local file to upload.
        """
        pass

    @abstractmethod
    def list_urls(self, prefix_url: str) -> list[str]:
        """List the full URLs of all files that start with the given URL.

        Args:
            prefix_url: The start of the URLs to list, e.g. `s3://bucket/network=X/collection=Y/site=Z/date=2026-01`.

        Returns:
            Full URLs of the matching files.
        """
        pass

    @abstractmethod
    def delete(self, url: str) -> None:
        """Delete a single file from storage.

        Args:
            url: Full URL of the file.
        """
        pass

    def delete_all(self, prefix_url: str) -> None:
        """Delete every file whose URL starts with the given URL.

        Args:
            prefix_url: The start of the URLs to delete, e.g. `s3://bucket` to empty a whole bucket.
        """
        for url in self.list_urls(prefix_url):
            self.delete(url)


class S3StorageClient(StorageClient):
    """S3 implementation of StorageClient, suitable for AWS and LocalStack."""

    def __init__(
        self,
        aws_access_key_id: str | None,
        aws_secret_access_key: str | None,
        aws_region_name: str | None,
        endpoint_url: str | None = None,
    ):
        """Initialize an S3 client.

        Args:
            aws_access_key_id: AWS Access Key. If omitted, AWS defaults apply.
            aws_secret_access_key: AWS Secret Key. If omitted, AWS defaults apply.
            aws_region_name: AWS Region Name. If omitted, AWS defaults apply.
            endpoint_url: Optional - used for LocalStack/testing environments. If omitted, AWS defaults apply.
        """
        kwargs = {}
        if endpoint_url is not None:
            kwargs["endpoint_url"] = endpoint_url

        session = boto3.session.Session(
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            region_name=aws_region_name,
        )

        self.client = session.client("s3", **kwargs)

    @staticmethod
    def _split_distribution_url(url: str) -> tuple[str, str]:
        """Split an `s3://` URL into the bucket and key that boto3 needs.

        E.g. `s3://bucket/network=X/site=Y/date=2026-01-26/data.parquet` gives
        `("bucket", "network=X/site=Y/date=2026-01-26/data.parquet")`.

        Args:
            url: An `s3://` URL.

        Returns:
            The bucket and the key. The key is empty if the URL is just the bucket.

        Raises:
            ValueError: If the URL doesn't start with `s3://` or has no bucket.
        """
        if not url.startswith("s3://"):
            raise ValueError(f"Expected an s3:// URL, got: {url}")
        bucket, _, key = url.removeprefix("s3://").partition("/")
        if not bucket:
            raise ValueError(f"No bucket in URL: {url}")
        return bucket, key

    def get_bytes(self, url: str) -> bytes:
        bucket, key = self._split_distribution_url(url)
        obj = self.client.get_object(Bucket=bucket, Key=key)
        return obj["Body"].read()

    def put_bytes(self, url: str, data: bytes) -> None:
        bucket, key = self._split_distribution_url(url)
        self.client.put_object(Bucket=bucket, Key=key, Body=data)

    def download_file(self, url: str, local_path: Path) -> None:
        bucket, key = self._split_distribution_url(url)
        local_path.parent.mkdir(parents=True, exist_ok=True)
        self.client.download_file(bucket, key, str(local_path))

    def upload_file(self, url: str, local_path: Path) -> None:
        bucket, key = self._split_distribution_url(url)
        self.client.upload_file(str(local_path), bucket, key)

    def list_urls(self, prefix_url: str) -> list[str]:
        bucket, prefix = self._split_distribution_url(prefix_url)
        paginator = self.client.get_paginator("list_objects_v2")
        urls = []
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                urls.append(f"s3://{bucket}/{obj['Key']}")  # type: ignore[typeddict-item]
        return urls

    def delete(self, url: str) -> None:
        bucket, key = self._split_distribution_url(url)
        self.client.delete_object(Bucket=bucket, Key=key)
