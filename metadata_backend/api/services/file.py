"""Service to retrieve file and bucket information from a file provider."""

import base64
import binascii
from abc import ABC, abstractmethod
from io import BytesIO

import aioboto3
import botocore.exceptions
import ujson
from crypt4gh.keys import c4gh
from crypt4gh.lib import encrypt
from pydantic import BaseModel, RootModel

from ...conf.c4gh import c4gh_config
from ...conf.s3 import s3_config
from ...helpers.logger import LOG
from ...services.admin_service import AdminServiceHandler
from ...services.keystone_service import KeystoneServiceHandler
from ..exceptions import SystemException, UserException
from ..models.models import File as SubmissionFile
from ..models.sda import FileItem


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
            raise UserException(reason)

        size = await self._verify_user_file(bucket, file)
        if size is None:
            reason = f"File '{file}' does not exist in bucket '{bucket}'."
            LOG.error(reason)
            raise UserException(reason)
        if size == 0:
            reason = f"File '{file}' is empty."
            LOG.error(reason)
            raise UserException(reason)
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
            raise UserException(reason)

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
            raise UserException(reason)

        files = await self._list_files_in_bucket(bucket)
        if not files.root:
            reason = f"No files found in bucket '{bucket}'."
            LOG.error(reason)
            raise UserException(reason)
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

    async def find_missing_files(self, user_id: str, submission_id: str, files: list[SubmissionFile]) -> list[str]:
        """Return file paths that are missing from the provider."""
        raise SystemException("Configured file provider does not support inbox file checks.")

    async def find_orphaned_files(self, user_id: str, submission_id: str, files: list[SubmissionFile]) -> list[str]:
        """Return file paths that are present in the provider but not referenced in the submission files."""
        raise SystemException("Configured file provider does not support orphaned file checks.")

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

        # Initialize the base S3 session with static credentials when available.
        session_kwargs: dict[str, str] = {"region_name": self._config.S3_REGION}
        if self._config.STATIC_S3_ACCESS_KEY_ID and self._config.STATIC_S3_SECRET_ACCESS_KEY:
            session_kwargs["aws_access_key_id"] = self._config.STATIC_S3_ACCESS_KEY_ID
            session_kwargs["aws_secret_access_key"] = self._config.STATIC_S3_SECRET_ACCESS_KEY
        self._session = aioboto3.Session(**session_kwargs)
        self.region = self._config.S3_REGION
        self.endpoint = self._config.S3_ENDPOINT

    async def _verify_user_file(self, bucket: str, file: str) -> int | None:
        """
        Verify that the file exists in the specified S3 bucket and return its size.

        Args:
            bucket: The name of the S3 bucket.
            file: The file path in the bucket.

        Returns:
            The file size in bytes if the file exists, otherwise None.
        """
        async with self._session.client("s3", endpoint_url=self.endpoint) as s3:
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
        async with self._session.client("s3", endpoint_url=self.endpoint) as s3:
            try:
                response = await s3.list_objects_v2(Bucket=bucket)
                contents = response.get("Contents", [])
                files = [self.File(path=f"S3://{bucket}/{obj['Key']}", bytes=int(obj["Size"])) for obj in contents]
                return self.Files(files)
            except botocore.exceptions.ClientError as e:
                err = e.response.get("Error", {})
                code = err.get("Code")
                msg = err.get("Message")

                if code == "NoSuchBucket":
                    raise UserException("Bucket does not exist") from e

                LOG.exception("Failed to list files in bucket: %s — %s", code, msg)
                raise SystemException("Failed to list files in bucket") from e


class S3AllasFileProviderService(S3FileProviderService):
    """Service to manage S3 buckets in Allas."""

    def __init__(self) -> None:
        """Create S3 Allas file service."""
        super().__init__()
        self.api_project_id = self._config.SD_SUBMIT_PROJECT_ID

    def _require_api_project_id(self) -> str:
        """Return SD Submit project id or raise if missing."""
        if not self.api_project_id:
            reason = "S3 bucket policy operations require SD_SUBMIT_PROJECT_ID (CSC deployment)."
            LOG.error(reason)
            raise SystemException(reason)
        return self.api_project_id

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

        api_project_id = self._require_api_project_id()

        policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Sid": "GrantSDSubmitReadAccess",
                    "Effect": "Allow",
                    "Principal": {
                        "AWS": f"arn:aws:iam::{api_project_id}:root",
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
            err = e.response.get("Error", {})
            code = err.get("Code")
            msg = err.get("Message")

            if code == "NoSuchBucket":
                raise UserException("Bucket does not exist") from e

            LOG.exception("Failed to update bucket policy: %s — %s", code, msg)
            raise SystemException("Failed to update bucket policy") from e

    async def _verify_bucket_policy(self, bucket: str) -> bool:
        """Verify that the read access policy has been assigned to a bucket.

        Args:
            bucket: The name of the S3 bucket.
        Returns:
            True if the policy is assigned, False otherwise."""
        async with self._session.client("s3", endpoint_url=self.endpoint) as s3:
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

        api_project_id = self._require_api_project_id()

        policy = ujson.loads(resp["Policy"])
        for statement in policy["Statement"]:
            if statement["Sid"] == "GrantSDSubmitReadAccess":
                if statement["Principal"]["AWS"] == f"arn:aws:iam::{api_project_id}:root":
                    return True

        return False


class S3InboxSDAService(FileProviderService):
    """Service to manage S3 buckets in NeIC SDA S3 Inbox."""

    def __init__(self, admin_handler: AdminServiceHandler) -> None:
        """Create S3 file service."""

        self._config = s3_config()
        self.region = self._config.S3_REGION
        self.endpoint = self._config.S3_ENDPOINT
        self._admin_handler = admin_handler

    async def _verify_user_file(self, bucket: str, file: str) -> int | None:
        """Verify that the file exists in the specified S3 bucket and return its size."""
        return None

    async def _list_buckets(self, credentials: KeystoneServiceHandler.EC2Credentials) -> list[str]:
        """List all buckets.

        NBIS submissions use the SDA inbox instead of Allas bucket management.
        """
        return []

    async def _list_files_in_bucket(self, bucket: str) -> FileProviderService.Files:
        """List all files in the specified bucket."""
        return self.Files([])

    async def _update_bucket_policy(self, bucket: str, creds: KeystoneServiceHandler.EC2Credentials) -> None:
        """Assign a read access policy to the specified bucket."""
        reason = "Bucket policy operations are not supported for SDA inbox submissions."
        LOG.error(reason)
        raise UserException(reason)

    async def _verify_bucket_policy(self, bucket: str) -> bool:
        """Verify that the read access policy has been assigned to a bucket."""
        return False

    async def find_missing_files(self, user_id: str, submission_id: str, files: list[SubmissionFile]) -> list[str]:
        """Return file paths that are currently missing from the S3 inbox.

        :param user_id: The ID of the user
        :param submission_id: The ID of the submission (= dataset accession ID)
        :param files: The list of submission files
        :returns: The list of any missing file paths
        """
        inbox_files: list[FileItem] = await self._admin_handler.get_user_files(user_id, submission_id)
        inbox_paths = {inbox_file.inbox_path for inbox_file in inbox_files}
        # We assume that the path value of submission files are a precise match with the paths listed in the inbox
        return [file.path for file in files if file.path not in inbox_paths]

    async def find_orphaned_files(self, user_id: str, submission_id: str, files: list[SubmissionFile]) -> list[str]:
        """Return file paths that are present in the S3 inbox but not referenced in the submission files.

        :param user_id: The ID of the user
        :param submission_id: The ID of the submission (= dataset accession ID)
        :param files: The list of submission files
        :returns: The list of any orphaned file paths
        """
        inbox_files: list[FileItem] = await self._admin_handler.get_user_files(user_id, submission_id)
        inbox_paths = {inbox_file.inbox_path for inbox_file in inbox_files}
        submission_paths = {file.path for file in files}
        return [inbox_path for inbox_path in inbox_paths if inbox_path not in submission_paths]

    async def _load_crypt4gh_keys(self) -> tuple[object, object]:
        """Load Crypt4GH sender secret and recipient public keys from env variables."""
        conf = c4gh_config()
        try:
            sender_key_pem = base64.b64decode(conf.CRYPT4GH_PRIVATE_KEY).decode("utf-8")
            recipient_key_pem = base64.b64decode(conf.CRYPT4GH_PUBLIC_KEY).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError) as ex:
            raise SystemException("Invalid base64 in C4GH key environment variables.") from ex

        try:
            sender_lines = [line.strip().encode("utf-8") for line in sender_key_pem.splitlines() if line.strip()]
            recipient_lines = [line.strip().encode("utf-8") for line in recipient_key_pem.splitlines() if line.strip()]

            private_data = base64.b64decode(b"".join(sender_lines[1:-1]))
            public_data = base64.b64decode(b"".join(recipient_lines[1:-1]))

            private_stream = BytesIO(private_data)
            if private_data.startswith(c4gh.MAGIC_WORD):
                private_stream.seek(len(c4gh.MAGIC_WORD))

            sender_secret_key = c4gh.parse_private_key(private_stream, lambda: conf.CRYPT4GH_PRIVATE_KEY_PASSPHRASE)
            recipient_public_key = public_data
            return sender_secret_key, recipient_public_key
        except Exception as ex:
            raise SystemException("Failed to load Crypt4GH keys for Bigpicture metadata encryption.") from ex

    async def _encrypt_file(self, file: bytes, sender_secret_key: object, recipient_public_key: object) -> bytes:
        """Encrypt file bytes using crypt4gh and return encrypted payload bytes."""
        infile = BytesIO(file)
        outfile = BytesIO()
        encrypt([(0, sender_secret_key, recipient_public_key)], infile, outfile)
        return outfile.getvalue()

    async def _add_file_to_bucket(
        self,
        bucket_name: str,
        object_key: str,
        access_key: str,
        secret_key: str,
        session_token: str,
        body: bytes = b"",
    ) -> None:
        """Put a C4GH encrypted object to S3 bucket using provided credentials.

        :param bucket_name: name of the bucket
        :param object_key: key for the object to be added
        :param access_key: S3 access key ID
        :param secret_key: S3 secret access key
        :param session_token: S3 session token
        :param body: unencrypted object bytes
        """
        sender_secret_key, recipient_public_key = await self._load_crypt4gh_keys()
        encrypted_file = await self._encrypt_file(body, sender_secret_key, recipient_public_key)

        try:
            session = aioboto3.Session()
            async with session.client(
                "s3",
                endpoint_url=self.endpoint,
                aws_access_key_id=access_key,
                aws_secret_access_key=secret_key,
                aws_session_token=session_token,  # equivalent to s3cmd access_token
                region_name=self.region,
            ) as s3:
                await s3.put_object(
                    Bucket=bucket_name,
                    Key=object_key,
                    Body=encrypted_file,
                    ContentType="application/octet-stream",
                )
        except botocore.exceptions.ClientError as ex:
            err = ex.response.get("Error", {})
            code = err.get("Code")
            msg = err.get("Message")
            LOG.exception(
                "Failed to upload encrypted file to SDA inbox bucket '%s' key '%s': %s - %s",
                bucket_name,
                object_key,
                code,
                msg,
            )
            raise SystemException("Failed to upload encrypted file to SDA inbox.") from ex
