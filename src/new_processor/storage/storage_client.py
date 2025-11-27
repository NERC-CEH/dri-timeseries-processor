from abc import ABC, abstractmethod
from pathlib import Path

import boto3


class StorageClient(ABC):
    """Abstract base class defining methods for retrieving and writing data."""

    @abstractmethod
    def get_bytes(self, bucket: str, key: str) -> bytes:
        """Retrieve data from the underlying storage.

        Args:
            bucket: Where data should be found.
            key: Name of object containing the data.

        Returns:
            The full contents of the data as a bytestring.
        """
        pass

    @abstractmethod
    def put_bytes(self, bucket: str, key: str, data: bytes) -> None:
        """Write data to the underlying storage.

        Args:
            bucket: Where data should be stored.
            key: Name of object containing the data.
            data: The bytes to be written.
        """
        pass

    @abstractmethod
    def list_keys(self, bucket: str) -> list[str]:
        """List all the keys in storage.

        Args:
            bucket: Where to look for keys
        """
        pass

    @abstractmethod
    def delete_key(self, bucket: str, key: str) -> None:
        """Delete from the underlying storage.

        Args:
            bucket: Where data should be deleted from
            key: Name of object to be deleted
        """
        pass

    @abstractmethod
    def clear_bucket(self, bucket: str) -> None:
        """Clear all files from a bucket

        Args:
            bucket: Where data should be deleted from
        """
        pass


class S3StorageClient(StorageClient):
    """S3 implementation of StorageClient, suitable for AWS and LocalStack."""

    def __init__(self, endpoint_url: str | None = None):
        """Initialize an S3 client.

        Args:
            endpoint_url: Optional - used for LocalStack/testing environments. If omitted, AWS defaults apply.
        """
        kwargs = {}
        if endpoint_url is not None:
            kwargs["endpoint_url"] = endpoint_url

        self.client = boto3.client("s3", **kwargs)

    def get_bytes(self, bucket: str, key: str) -> bytes:
        """Retrieve data from the S3 storage.

        Args:
            bucket: S3 bucket name.
            key: Key identifying the object within the bucket.

        Returns:
            The contents of the object as a bytestring.
        """
        obj = self.client.get_object(Bucket=bucket, Key=key)
        return obj["Body"].read()

    def put_bytes(self, bucket: str, key: str, data: bytes) -> None:
        """Write to the S3 storage.

        Args:
            bucket: S3 bucket name.
            key: Target key for the uploaded object.
            data: Data to write to S3.
        """
        self.client.put_object(Bucket=bucket, Key=key, Body=data)

    def list_keys(self, bucket: str) -> list[str]:
        """List all the keys in S3 bucket.

        Args:
            bucket: S3 bucket name.
        """
        resp = self.client.list_objects_v2(Bucket=bucket)
        return [obj["Key"] for obj in resp.get("Contents", [])]

    def clear_bucket(self, bucket: str) -> None:
        """Clear all from the S3 bucket.

        Args:
            bucket: S3 bucket name.
        """
        keys = self.list_keys(bucket)
        for s3_key in keys:
            self.delete_key(bucket, s3_key)

    def delete_key(self, bucket: str, key: str) -> None:
        """Delete single key from the S3 bucket.

        Args:
            bucket: S3 bucket name.
            key: S3 key to delete.
        """
        self.client.delete_object(Bucket=bucket, Key=key)


class LocalFilesystemStorageClient(StorageClient):
    """Local file system implementation of StorageClient, suitable for local development and testing."""

    def __init__(self, base_dir: str | Path):
        """Initialize a local storage client.

        Args:
            base_dir: Directory treated as the storage root. "Buckets" are assumed to be subdirectories under base.
        """
        self.base_dir = Path(base_dir)

    def _resolve_path(self, bucket: Path, key: Path) -> Path:
        """Combine base, bucket, key into a filesystem path.

        Args:
           bucket: Subdirectory under the base directory.
           key: Path under bucket to the actual file.

        Returns:
           A Path object for the requested file.
        """
        return self.base_dir / Path(bucket) / Path(key)

    def get_bytes(self, bucket: str | Path, key: str | Path) -> bytes:
        """Read from the local filesystem.

        Args:
            bucket: Subdirectory under the base directory.
            key: Path under bucket to the actual file.

        Returns:
            File contents as bytes.
        """
        path = self._resolve_path(bucket, key)
        return path.read_bytes()

    def put_bytes(self, bucket: str | Path, key: str | Path, data: bytes) -> None:
        """Write to the local filesystem.

        Args:
            bucket: Target subdirectory under the base directory.
            key: Target path under bucket to the file to write.
            data: Data to write.
        """
        path = self._resolve_path(bucket, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def list_keys(self, bucket: str) -> list[str]:
        """List all the files in the directory.

        Args:
            bucket: Target subdirectory under the base directory.
        """
        bucket_path = self.base_dir / bucket
        keys = [p.relative_to(bucket_path).as_posix() for p in bucket_path.rglob("*") if p.is_file()]
        return keys

    def clear_bucket(self, bucket: str) -> None:
        """Clear all the files in the directory.

        Args:
            bucket: Target subdirectory under the base directory.
        """
        keys = self.list_keys(bucket)
        for s3_key in keys:
            self.delete_key(bucket, s3_key)

    def delete_key(self, bucket: str | Path, key: str | Path) -> None:
        """Delete file in the directory.

        Args:
            bucket: Target subdirectory under the base directory.
            key: File to delete.
        """
        path = self._resolve_path(Path(bucket), Path(key))
        if path.exists():
            path.unlink()
