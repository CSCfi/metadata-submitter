"""Service to verify that the submitted file exists."""

import os
from abc import ABC, abstractmethod

import aioboto3
import botocore.exceptions
import ujson
from aiohttp import web
from pydantic import BaseModel, RootModel

from ...helpers.logger import LOG

S3_ACCESS_KEY_ENV = "S3_ACCESS_KEY"  # nosec
S3_SECRET_KEY_ENV = "S3_SECRET_KEY"  # nosec
S3_REGION_ENV = "S3_REGION"
S3_ENDPOINT_ENV = "S3_ENDPOINT"


class FileProviderService(ABC):
    """Service to retrieve file and bucket information from a file provider."""

    class File(BaseModel):
        """Model for file metadata."""

        path: str
        bytes: int

    class Files(RootModel[list[File]]):
        """Model for a list of file metadata."""

    async def verify_user_file(self, bucket: str, file: str) -> int | None:
        """
        Verify that the file exists in the specified bucket and return its size.

        Args:
            bucket: The name of the bucket.
            file: The file path in the bucket.

        Returns:
            The file size in bytes if the file exists, otherwise None.
        """
        size = await self._verify_user_file(bucket, file)
        if size is None:
            reason = f"File '{file}' does not exist in '{bucket}'."
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)
        if size == 0:
            reason = f"File '{file}' is empty."
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)
        return size

    async def list_buckets(self, project_id: str) -> list[str]:
        """
        List all available buckets.

        Args:
            project_id: The ID of the project.

        Returns:
            A list of buckets found.
        """
        buckets = await self._list_buckets()
        buckets_with_policy = []
        for bucket in buckets:
            has_policy = await self._verify_bucket_policy(bucket, project_id)
            if has_policy:
                buckets_with_policy.append(bucket)

        if not buckets_with_policy:
            reason = "No buckets found."
            LOG.error(reason)
            raise web.HTTPNotFound(reason=reason)

        return buckets_with_policy

    async def list_files_in_bucket(self, bucket: str, project_id: str) -> Files:
        """
        List files in the specified bucket.

        Args:
            bucket: The name of the bucket.
            project_id: The ID of the project.

        Returns:
            A list of files (objects) found.
        """
        if not await self._verify_bucket_policy(bucket, project_id):
            reason = f"Bucket {bucket} is not accessible in project {project_id}."
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)

        files = await self._list_files_in_bucket(bucket)
        if not files.root:
            reason = f"No files found in '{bucket}'."
            LOG.error(reason)
            raise web.HTTPNotFound(reason=reason)
        return files

    async def update_bucket_policy(self, bucket: str, project_id: str) -> None:
        """
        Assign a read access policy to the specified bucket.

        Args:
            bucket: The name of the bucket.
            project_id: The ID of the project.
        """
        await self._update_bucket_policy(bucket, project_id)

    async def verify_bucket_policy(self, bucket: str, project_id: str) -> bool:
        """
        Verify that the read access policy has been assigned to a bucket.

        Args:
            bucket: The name of the bucket.
            project_id: The ID of the project.

        Returns:
            True if the policy is assigned, False otherwise.
        """
        return await self._verify_bucket_policy(bucket, project_id)

    @abstractmethod
    async def _verify_user_file(self, bucket: str, file: str) -> int | None:
        """
        Verify that the file exists in the specified bucket and return its size.

        Args:
            bucket: The name of the bucket.
            file: The file path in the bucket.

        Returns:
            The file size in bytes if the file exists, otherwise None.
        """

    @abstractmethod
    async def _list_buckets(self) -> list[str]:
        """
        List all buckets.

        Returns:
            A list of bucket names.
        """

    @abstractmethod
    async def _list_files_in_bucket(self, bucket: str) -> Files:
        """
        List all files in the specified bucket.

        Args:
            bucket: The name of the bucket.

        Returns:
            A list of files (objects) found.
        """

    @abstractmethod
    async def _update_bucket_policy(self, bucket: str, project_id: str) -> None:
        """
        Assign a read access policy to the specified bucket.

        Args:
            bucket: The name of the bucket.
            project_id: The ID of the project.
        """

    @abstractmethod
    async def _verify_bucket_policy(self, bucket: str, project_id: str) -> bool:
        """
        Verify that the read access policy has been assigned to a bucket.

        Args:
            bucket: The name of the bucket.
            project_id: The ID of the project.

        Returns:
            True if the policy is assigned, False otherwise.
        """


class S3FileProviderService(FileProviderService):
    """Service to retrieve file and bucket information from S3 storage."""

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

    async def _verify_user_file(self, bucket: str, file: str) -> int | None:
        """
        Verify that the file exists in the specified S3 bucket and return its size.

        Args:
            bucket: The name of the S3 bucket.
            file: The file path in the bucket.

        Returns:
            The file size in bytes if the file exists, otherwise None.
        """
        async with self._session.client("s3", endpoint_url=self.endpoint, use_ssl=False) as s3:
            try:
                resp = await s3.head_object(
                    Bucket=bucket,
                    Key=file,
                )
                return int(resp["ContentLength"])
            except botocore.exceptions.ClientError as e:
                if e.response["ResponseMetadata"]["HTTPStatusCode"] == 404:
                    return None
                raise e

    async def _list_buckets(self) -> list[str]:
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

    async def _list_files_in_bucket(self, bucket: str) -> FileProviderService.Files:
        """
        List all files in the specified S3 bucket.

        Args:
            bucket: The name of the S3 bucket.

        Returns:
            A list of files found.
        """
        async with self._session.client("s3", endpoint_url=self.endpoint, use_ssl=False) as s3:
            try:
                response = await s3.list_objects_v2(Bucket=bucket)
                contents = response.get("Contents", [])
                files = [self.File(path=f"S3://{bucket}/{obj['Key']}", bytes=int(obj["Size"])) for obj in contents]
                return self.Files(files)
            except botocore.exceptions.ClientError as e:
                if e.response["ResponseMetadata"]["HTTPStatusCode"] == 404:
                    raise web.HTTPBadRequest(reason=e.response["Error"]["Message"])
                raise e


class S3AllasFileProviderService(S3FileProviderService):
    """Service to manage S3 buckets in Allas."""

    async def _update_bucket_policy(self, bucket: str, project_id: str) -> None:
        """
        Assign a read access policy to the specified S3 bucket.

        Args:
            bucket: The name of the S3 bucket.
            project_id: The ID of the project.
        """
        async with self._session.client("s3", endpoint_url=self.endpoint, use_ssl=False) as s3:
            try:
                resp = await s3.get_bucket_policy(
                    Bucket=bucket,
                )
                policy = ujson.loads(resp["Policy"])
                for statement in policy["Statement"]:
                    if statement["Sid"] == "GrantSDSubmitReadAccess":
                        # Required policy statement already exists.
                        return
                statements = policy["Statement"]
            except Exception:
                statements = []

        policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Sid": "GrantSDSubmitReadAccess",
                    "Effect": "Allow",
                    "Principal": {
                        "AWS": f"arn:aws:iam::${project_id}:root",
                    },
                    "Action": ["s3:GetObject", "s3:ListBucket", "s3:GetBucketPolicy"],
                    "Resource": f"arn:aws:s3:::{bucket}/*",
                },
            ]
            + statements,
        }
        try:
            await s3.put_bucket_policy(
                Bucket=bucket,
                Policy=ujson.dumps(policy),
            )
        except botocore.exceptions.ClientError as e:
            if e.response["ResponseMetadata"]["HTTPStatusCode"] == 404:
                raise web.HTTPBadRequest(reason=e.response["Error"]["Message"])
            raise e

    async def _verify_bucket_policy(self, bucket: str, project_id: str) -> bool:
        """Verify that the read access policy has been assigned to a bucket."""
        async with self._session.client("s3", endpoint_url=self.endpoint, use_ssl=False) as s3:
            try:
                resp = await s3.get_bucket_policy(
                    Bucket=bucket,
                )
            except botocore.exceptions.ClientError as e:
                if e.response["ResponseMetadata"]["HTTPStatusCode"] == 404:
                    # Bucket does not exist or has no policy
                    return False
                LOG.error("Error verifying bucket policy: %s", e)
                raise e

        policy = ujson.loads(resp["Policy"])
        for statement in policy["Statement"]:
            if statement["Sid"] == "GrantSDSubmitReadAccess":
                if statement["Principal"]["AWS"] == f"arn:aws:iam::${project_id}:root":
                    return True

        return False
