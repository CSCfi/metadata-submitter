"""Service to retrieve file and bucket information from a file provider."""

from abc import ABC, abstractmethod

import aioboto3
import botocore.exceptions
import ujson
from aiohttp import web
from pydantic import BaseModel, RootModel

from ...conf.s3 import s3_config
from ...helpers.logger import LOG
from ...services.keystone_service import KeystoneServiceHandler


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
        if not await self._verify_bucket_policy(bucket):
            reason = f"Bucket '{bucket}' has not been made accessible to SD Submit."
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)

        size = await self._verify_user_file(bucket, file)
        if size is None:
            reason = f"File '{file}' does not exist in bucket '{bucket}'."
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)
        if size == 0:
            reason = f"File '{file}' is empty."
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)
        return size

    async def list_buckets(self, credentials: KeystoneServiceHandler.EC2Credentials) -> list[str]:
        """
        List all available buckets.

        Args:
            credentials: The EC2 credentials for the project.

        Returns:
            A list of buckets found.
        """
        buckets = await self._list_buckets(credentials)

        if not buckets:
            reason = "No buckets found."
            LOG.error(reason)
            raise web.HTTPNotFound(reason=reason)

        return buckets

    async def list_files_in_bucket(self, bucket: str) -> Files:
        """
        List files in the specified bucket.

        Args:
            bucket: The name of the bucket.

        Returns:
            A list of files (objects) found.
        """
        # Bucket must have been assigned the correct policy first
        if not await self._verify_bucket_policy(bucket):
            reason = f"Bucket '{bucket}' has not been made accessible to SD Submit."
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)

        files = await self._list_files_in_bucket(bucket)
        if not files.root:
            reason = f"No files found in bucket '{bucket}'."
            LOG.error(reason)
            raise web.HTTPNotFound(reason=reason)
        return files

    async def update_bucket_policy(self, bucket: str, creds: KeystoneServiceHandler.EC2Credentials) -> None:
        """
        Assign a read access policy to the specified bucket.

        This will make it possible for the API to read its files with static EC2 credentials.

        Args:
            bucket: The name of the bucket.
            creds: Project specific EC2 credentials of the user.
        """
        await self._update_bucket_policy(bucket, creds)

    async def verify_bucket_policy(self, bucket: str) -> bool:
        """
        Verify that the read access policy has been assigned to a bucket.

        Args:
            bucket: The name of the bucket.

        Returns:
            True if the policy is assigned, False otherwise.
        """
        return await self._verify_bucket_policy(bucket)

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
    async def _list_buckets(self, credentials: KeystoneServiceHandler.EC2Credentials) -> list[str]:
        """
        List all buckets.

        Args:
            credentials: The EC2 credentials for the project.

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
    async def _update_bucket_policy(self, bucket: str, creds: KeystoneServiceHandler.EC2Credentials) -> None:
        """
        Assign a read access policy to the specified bucket.

        Args:
            bucket: The name of the bucket.
            creds: The EC2 credentials of the user for the project.
        """

    @abstractmethod
    async def _verify_bucket_policy(self, bucket: str) -> bool:
        """
        Verify that the read access policy has been assigned to a bucket.

        Args:
            bucket: The name of the bucket.

        Returns:
            True if the policy is assigned, False otherwise.
        """


class S3FileProviderService(FileProviderService, ABC):
    """Service to retrieve file and bucket information from S3 storage."""

    def __init__(self) -> None:
        """Create S3 file service."""

        self._config = s3_config()

        # Initialize the base S3 session with static credentials.
        self._session = aioboto3.Session(
            aws_access_key_id=self._config.STATIC_S3_ACCESS_KEY_ID,
            aws_secret_access_key=self._config.STATIC_S3_SECRET_ACCESS_KEY,
            region_name=self._config.S3_REGION,
        )
        self.region = self._config.S3_REGION
        self.endpoint = self._config.S3_ENDPOINT
        self.api_project_id = self._config.SD_SUBMIT_PROJECT_ID

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
                    # File does not exist
                    return None
                LOG.error("Error verifying user file: %s", e)
                raise e

    async def _list_buckets(self, creds: KeystoneServiceHandler.EC2Credentials) -> list[str]:
        """
        List all available S3 buckets with user's project scoped credentials.

        Args:
            creds: The EC2 credentials for the project.

        Returns:
            A list of bucket names.
        """
        session = aioboto3.Session()
        async with session.client(
            "s3",
            endpoint_url=self.endpoint,
            aws_access_key_id=creds.access,
            aws_secret_access_key=creds.secret,
            region_name=self.region,
            use_ssl=False,
        ) as s3:
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

    async def _update_bucket_policy(self, bucket: str, creds: KeystoneServiceHandler.EC2Credentials) -> None:
        """
        Assign a read access policy to the specified S3 bucket.

        Args:
            bucket: The name of the S3 bucket.
            creds: EC2 credentials for the project.
        """
        session = aioboto3.Session()
        async with session.client(
            "s3",
            endpoint_url=self.endpoint,
            aws_access_key_id=creds.access,
            aws_secret_access_key=creds.secret,
            region_name=self.region,
            use_ssl=False,
        ) as s3:
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
                        "AWS": f"arn:aws:iam::{self.api_project_id}:root",
                    },
                    "Action": ["s3:GetObject", "s3:ListBucket", "s3:GetBucketPolicy"],
                    "Resource": [f"arn:aws:s3:::{bucket}", f"arn:aws:s3:::{bucket}/*"],
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

    async def _verify_bucket_policy(self, bucket: str) -> bool:
        """Verify that the read access policy has been assigned to a bucket.

        Args:
            bucket: The name of the S3 bucket.
        Returns:
            True if the policy is assigned, False otherwise."""
        async with self._session.client("s3", endpoint_url=self.endpoint, use_ssl=False) as s3:
            try:
                resp = await s3.get_bucket_policy(
                    Bucket=bucket,
                )
            except botocore.exceptions.ClientError as e:
                if e.response["ResponseMetadata"]["HTTPStatusCode"] in (403, 404):
                    # Bucket does not exist or has no policy
                    return False
                LOG.error("Error verifying bucket policy: %s", e)
                raise e

        policy = ujson.loads(resp["Policy"])
        for statement in policy["Statement"]:
            if statement["Sid"] == "GrantSDSubmitReadAccess":
                if statement["Principal"]["AWS"] == f"arn:aws:iam::{self.api_project_id}:root":
                    return True

        return False
