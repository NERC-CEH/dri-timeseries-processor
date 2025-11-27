from abc import ABC, abstractmethod

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

    def __init__(self, aws_access_key_id, aws_secret_access_key, region_name, endpoint_url: str | None = None):
        """Initialize an S3 client.

        Args:
            endpoint_url: Optional - used for LocalStack/testing environments. If omitted, AWS defaults apply.
        """
        kwargs = {}
        if endpoint_url is not None:
            kwargs["endpoint_url"] = endpoint_url

        session = boto3.session.Session(
            aws_access_key_id=aws_access_key_id, aws_secret_access_key=aws_secret_access_key, region_name=region_name
        )

        self.client = session.client("s3", **kwargs)

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
