"""Service to verify that the submitted file exists."""

import os
from abc import ABC, abstractmethod

import aioboto3
import botocore.exceptions
from aiohttp import web
from pydantic import BaseModel, RootModel

from ...helpers.logger import LOG

S3_ACCESS_KEY_ENV = "S3_ACCESS_KEY"  # nosec
S3_SECRET_KEY_ENV = "S3_SECRET_KEY"  # nosec
S3_REGION_ENV = "S3_REGION"
S3_ENDPOINT_ENV = "S3_ENDPOINT"


class FileProviderService(ABC):
    """Service to verify that the submitted file exists."""

    class File(BaseModel):
        """Model for file metadata."""

        path: str
        bytes: int

    class Files(RootModel[list[File]]):
        """Model for a list of file metadata."""

    async def verify_user_file(self, folder: str, file: str) -> int | None:
        """
        Verify that the file exists in the specified folder and return its size.

        Args:
            folder: The name of the folder.
            file: The file path in the folder.

        Returns:
            The file size in bytes if the file exists, otherwise None.
        """
        size = await self._verify_user_file(folder, file)
        if size is None:
            reason = f"File '{file}' does not exist in '{folder}'."
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)
        if size == 0:
            reason = f"File '{file}' is empty."
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)
        return size

    async def list_folders(self) -> list[str]:
        """
        List all available folders.

        Returns:
            A list of folders found.
        """
        folders = await self._list_folders()
        if not folders:
            reason = "No folders found."
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)
        return folders

    async def list_files_in_folder(self, folder: str) -> Files:
        """
        List files in the specified folder.

        Args:
            folder: The name of the folder.

        Returns:
            A list of files (objects) found.
        """
        files = await self._list_files_in_folder(folder)
        if not files.root:
            reason = f"No files found in '{folder}'."
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)
        return files

    @abstractmethod
    async def _verify_user_file(self, folder: str, file: str) -> int | None:
        """
        Verify that the file exists in the specified folder and return its size.

        Args:
            folder: The name of the folder.
            file: The file path in the folder.

        Returns:
            The file size in bytes if the file exists, otherwise None.
        """

    @abstractmethod
    async def _list_folders(self) -> list[str]:
        """
        List all available folders.

        Returns:
            A list of folder names.
        """

    @abstractmethod
    async def _list_files_in_folder(self, folder: str) -> Files:
        """
        List all files in the specified folder.

        Args:
            folder: The name of the folder.

        Returns:
            A list of files (objects) found.
        """


class S3FileProviderService(FileProviderService):
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
        async with self._session.client("s3", endpoint_url=self.endpoint, use_ssl=False) as s3:
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

    async def _list_folders(self) -> list[str]:
        """
        List all available S3 buckets.

        Returns:
            A list of bucket names.
        """
        async with self._session.client("s3", endpoint_url=self.endpoint, use_ssl=False) as s3:
            try:
                response = await s3.list_buckets()
                buckets = response.get("Buckets", [])
                return [bucket["Name"] for bucket in buckets]
            except botocore.exceptions.ClientError as e:
                if e.response["ResponseMetadata"]["HTTPStatusCode"] == 404:
                    return []
                raise e

    async def _list_files_in_folder(self, folder: str) -> FileProviderService.Files:
        """
        List all files in the specified S3 bucket.

        Args:
            folder: The name of the S3 bucket.

        Returns:
            A list of files found.
        """
        async with self._session.client("s3", endpoint_url=self.endpoint, use_ssl=False) as s3:
            try:
                response = await s3.list_objects_v2(Bucket=folder)
                contents = response.get("Contents", [])
                files = [self.File(path=f"S3://{folder}/{obj['Key']}", bytes=int(obj["Size"])) for obj in contents]
                return self.Files(files)
            except botocore.exceptions.ClientError as e:
                if e.response["ResponseMetadata"]["HTTPStatusCode"] == 404:
                    raise web.HTTPBadRequest(reason=e.response["Error"]["Message"])
                raise e
