"""Service to verify that the submitted file exists."""

import os
from abc import ABC, abstractmethod

import aioboto3
import botocore.exceptions
from aiohttp import web

S3_ACCESS_KEY_ENV = "S3_ACCESS_KEY"  # nosec
S3_SECRET_KEY_ENV = "S3_SECRET_KEY"  # nosec
S3_REGION_ENV = "S3_REGION"
S3_ENDPOINT_ENV = "S3_ENDPOINT"


class FileService(ABC):
    """Service to verify that the submitted file exists."""

    async def verify_user_file(self, folder: str, file: str) -> int | None:
        """
        Verify that the file exists in the specified file or bucket and return its size.

        Args:
            folder: The name of the folder or bucket.
            file: The file path in the folder or bucket.

        Returns:
            The file size in bytes if the file exists, otherwise None.
        """
        size = await self._verify_user_file(folder, file)
        if size is None:
            raise web.HTTPBadRequest(reason=f"File '{file}' does not exist in '{folder}'.")
        if size == 0:
            raise web.HTTPBadRequest(reason=f"File '{file}' is empty.")
        return size

    @abstractmethod
    async def _verify_user_file(self, folder: str, file: str) -> int | None:
        """
        Verify that the file exists in the specified file or bucket and return its size.

        Args:
            folder: The name of the folder or bucket.
            file: The file path in the folder or bucket.

        Returns:
            The file size in bytes if the file exists, otherwise None.
        """


class S3FileService(FileService):
    """Service to verify that the submitted file exists in S3."""

    def __init__(self) -> None:
        """Create S3 file service."""

        def _env(key: str, default_value: str | None = None) -> str:
            value = os.getenv(key, default_value)
            if value is None:
                raise RuntimeError(f"Missing required environment variable: {key}")
            return value

        access_key = _env(S3_ACCESS_KEY_ENV)
        secret_key = _env(S3_SECRET_KEY_ENV)
        region = _env(S3_REGION_ENV)
        self.endpoint = _env(S3_ENDPOINT_ENV)

        """Initialize the S3 session."""
        self._session = aioboto3.Session(
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
        )

    async def _verify_user_file(self, folder: str, file: str) -> int | None:
        """
        Verify that the file exists in the specified S3 bucket and return its size.

        Args:
            folder: The name of the S3 bucket.
            file: The file path in the bucket.

        Returns:
            The file size in bytes if the file exists, otherwise None.
        """
        async with self._session.client("s3", endpoint_url=self.endpoint) as s3:
            try:
                resp = await s3.head_object(
                    Bucket=folder,
                    Key=file,
                )
                return int(resp["ContentLength"])
            except botocore.exceptions.ClientError as e:
                if e.response["ResponseMetadata"]["HTTPStatusCode"] == 404:
                    return None
                raise e
