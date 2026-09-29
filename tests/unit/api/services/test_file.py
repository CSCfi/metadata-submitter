import socket
from base64 import b64encode
from io import BytesIO
from unittest.mock import AsyncMock

import pytest
import ujson
from aiobotocore import session
from crypt4gh.lib import decrypt
from moto.server import ThreadedMotoServer
from pydantic import ValidationError

from metadata_backend.api.exceptions import SystemException, UserException
from metadata_backend.api.models.models import File as SubmissionFile
from metadata_backend.api.models.sda import FileItem
from metadata_backend.api.services.bigpicture import read_bp_public_key
from metadata_backend.api.services.crypt import Crypt4GHPublicKeyProvider, parse_private_key
from metadata_backend.api.services.file import S3AllasFileProviderService, S3InboxSDAService
from metadata_backend.conf.s3 import s3_config
from metadata_backend.services.keystone_service import KeystoneServiceHandler
from tests.utils import generate_crypt4gh_keypair_env_values

bucket = "test-bucket"
file = "test-file"
content = b"test"
creds = KeystoneServiceHandler.EC2Credentials(access="test-id", secret="test-key")


def _key_provider() -> Crypt4GHPublicKeyProvider:
    return Crypt4GHPublicKeyProvider(read_bp_public_key)


def _mock_key_provider() -> Crypt4GHPublicKeyProvider:
    """A key provider for tests that do not encrypt."""

    return AsyncMock(spec=Crypt4GHPublicKeyProvider)


@pytest.fixture(autouse=True)
async def s3_endpoint(monkeypatch):
    # Create moto server.
    s = socket.socket()
    s.bind(("", 0))
    port = s.getsockname()[1]
    s.close()

    server = ThreadedMotoServer(port=port)
    server.start()
    endpoint = f"http://localhost:{port}"

    # Set endpoint after server starts
    monkeypatch.setenv("S3_ENDPOINT", endpoint)

    # Cleanup S3 before each test
    sess = session.get_session()
    async with sess.create_client(
        "s3", endpoint_url=endpoint, aws_access_key_id="test", aws_secret_access_key="test", region_name="us-east-1"
    ) as s3:
        response = await s3.list_buckets()
        for bucket in response.get("Buckets", []):
            # Delete all objects in the bucket
            objects = await s3.list_objects_v2(Bucket=bucket["Name"])
            for obj in objects.get("Contents", []):
                await s3.delete_object(Bucket=bucket["Name"], Key=obj["Key"])
            # Delete the bucket
            await s3.delete_bucket(Bucket=bucket["Name"])

    yield endpoint
    server.stop()


@pytest.mark.asyncio
async def test_verify_user_file_exists(s3_endpoint):
    service = S3AllasFileProviderService()
    session = service._session

    # Bucket and file does not exist.
    size = await service._verify_user_file(bucket, file)
    assert size is None
    with pytest.raises(UserException):
        await service.verify_user_file(bucket, file)

    async with session.client("s3", endpoint_url=s3_endpoint) as s3:
        # Create bucket.
        await s3.create_bucket(Bucket=bucket)

        # File does not exist.
        size = await service._verify_user_file(bucket, file)
        assert size is None
        with pytest.raises(UserException):
            await service.verify_user_file(bucket, file)

        # Create file.
        await s3.put_object(Bucket=bucket, Key=file, Body=content)

        # File exists.
        size = await service._verify_user_file(bucket, file)
        assert size == len(content)

        await service.update_bucket_policy(bucket, creds)
        size = await service.verify_user_file(bucket, file)
        assert size == len(content)


@pytest.mark.asyncio
async def test_list_buckets_and_files(s3_endpoint):
    service = S3AllasFileProviderService()
    session = service._session

    async with session.client("s3", endpoint_url=s3_endpoint) as s3:
        # No buckets yet
        with pytest.raises(UserException):
            await service.list_buckets(creds)

        # Create bucket
        await s3.create_bucket(Bucket=bucket)

        # Now one bucket should be returned
        buckets = await service.list_buckets(creds)
        assert buckets[0] == bucket

        # No files in bucket yet - an accessible empty bucket is not an error
        await service.update_bucket_policy(bucket, creds)
        files = await service.list_files_in_bucket(bucket)
        assert files.root == []

        # Add a file
        await s3.put_object(Bucket=bucket, Key=file, Body=content)

        # Now list_files_in_bucket should return the file
        files = await service.list_files_in_bucket(bucket)
        assert files.root[0].path == f"S3://{bucket}/{file}"
        assert files.root[0].bytes == len(content)


@pytest.mark.asyncio
async def test_update_and_verify_bucket_policy(s3_endpoint):
    service = S3AllasFileProviderService()
    session = service._session

    async with session.client("s3", endpoint_url=s3_endpoint) as s3:
        # Cannot assign to non-existent bucket
        with pytest.raises(UserException):
            resp = await service.update_bucket_policy(bucket, creds)
            await resp.json()
            assert resp.status == 400
            assert resp.detail == "The specified bucket does not exist."

        # Create bucket
        await s3.create_bucket(Bucket=bucket)
        assert not await service.verify_bucket_policy(bucket)

        await service.update_bucket_policy(bucket, creds)

        # Verify bucket policy
        resp = await s3.get_bucket_policy(Bucket=bucket)
        policy = ujson.loads(resp["Policy"])
        assert policy["Statement"][0]["Sid"] == "GrantSDSubmitReadAccess"
        assert policy["Statement"][0]["Principal"]["AWS"] == f"arn:aws:iam::{s3_config().SD_SUBMIT_PROJECT_ID}:root"
        assert policy["Statement"][0]["Resource"] == [f"arn:aws:s3:::{bucket}", f"arn:aws:s3:::{bucket}/*"]

        assert await service.verify_bucket_policy(bucket)


@pytest.mark.asyncio
async def test_encrypt_file_without_the_public_key(monkeypatch):
    monkeypatch.delenv("CRYPT4GH_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("CRYPT4GH_PUBLIC_KEY_URL", raising=False)

    with pytest.raises(ValidationError, match="CRYPT4GH_PUBLIC_KEY_URL or CRYPT4GH_PUBLIC_KEY is required"):
        _key_provider()


@pytest.mark.asyncio
async def test_encrypt_file_with_an_unusable_public_key(monkeypatch):
    monkeypatch.setenv("CRYPT4GH_PUBLIC_KEY", b64encode(b"not a PEM document").decode("utf-8"))

    service = S3InboxSDAService(AsyncMock(), _key_provider())

    # Make sure we don't get a SystemError.
    with pytest.raises(SystemException, match="Service configuration error"):
        await service._encrypt_file(b"<DATASET/>")


@pytest.mark.asyncio
async def test_encrypt_file_roundtrip_with_generated_keys(monkeypatch, tmp_path):
    """_encrypt_file should encrypt bytes that the recipient private key decrypts."""
    passphrase = "unit-test-passphrase"
    recipient_private_key, recipient_public_key = generate_crypt4gh_keypair_env_values(tmp_path, passphrase)

    monkeypatch.setenv("CRYPT4GH_PUBLIC_KEY", recipient_public_key)

    service = S3InboxSDAService(AsyncMock(), _key_provider())

    plaintext = b"<DATASET><ID>123</ID></DATASET>"
    encrypted = await service._encrypt_file(plaintext)

    assert encrypted
    assert encrypted != plaintext

    decrypted_out = BytesIO()
    decrypt([(0, parse_private_key(recipient_private_key, passphrase), None)], BytesIO(encrypted), decrypted_out)
    assert decrypted_out.getvalue() == plaintext


@pytest.mark.asyncio
async def test_encrypt_file_private_key_per_file(monkeypatch, tmp_path):
    """The sender private key is generated per file."""
    recipient_private_key, recipient_public_key = generate_crypt4gh_keypair_env_values(tmp_path, "unit-test-passphrase")

    monkeypatch.setenv("CRYPT4GH_PUBLIC_KEY", recipient_public_key)

    service = S3InboxSDAService(AsyncMock(), _key_provider())

    plaintext = b"<DATASET><ID>123</ID></DATASET>"
    first = await service._encrypt_file(plaintext)
    second = await service._encrypt_file(plaintext)

    assert first != second


async def test_sda_inbox_add_file_to_bucket_uploads_payload(s3_endpoint):
    service = S3InboxSDAService(AsyncMock(), _mock_key_provider())

    upload_body = b"plaintext-xml-payload"
    encrypted_body = b"encrypted-binary-payload"
    object_key = "DATASET_123/METADATA/dataset.xml.c4gh"

    # Create the target bucket first.
    sess = session.get_session()
    async with sess.create_client(
        "s3",
        endpoint_url=s3_endpoint,
        aws_access_key_id="test",
        aws_secret_access_key="test",
        region_name="us-east-1",
    ) as s3:
        await s3.create_bucket(Bucket=bucket)

    service._encrypt_file = AsyncMock(return_value=encrypted_body)

    await service._add_file_to_bucket(
        bucket,
        object_key,
        access_key="test",
        secret_key="test",
        session_token="",
        body=upload_body,
    )

    async with sess.create_client(
        "s3",
        endpoint_url=s3_endpoint,
        aws_access_key_id="test",
        aws_secret_access_key="test",
        region_name="us-east-1",
    ) as s3:
        response = await s3.get_object(Bucket=bucket, Key=object_key)
        body_bytes = await response["Body"].read()

    assert body_bytes == encrypted_body
    assert response["ContentType"] == "application/octet-stream"


def get_mock_admin_handler(inbox_file_paths: list[str]) -> AsyncMock:
    """Create a mock admin handler with the given inbox file paths."""
    admin_handler = AsyncMock()
    admin_handler.get_user_files.return_value = [
        FileItem(
            fileID="12345678-1234-4234-8234-1234567890ab",
            inboxPath=file_path,
            fileStatus="uploaded",
            createdAt="2024-01-01T00:00:00Z",
        )
        for file_path in inbox_file_paths
    ]
    return admin_handler


def get_submission_files(file_paths: list[str]) -> list[SubmissionFile]:
    """Create submission files with the given file paths."""
    return [SubmissionFile(path=file_path, bytes=100) for file_path in file_paths]


async def test_find_missing_files():
    # No missing files.
    admin_handler = get_mock_admin_handler(["IMAGES/IMAGE_1/img1.dcm"])
    submission_files = get_submission_files(["IMAGES/IMAGE_1/img1.dcm"])
    service = S3InboxSDAService(admin_handler, _mock_key_provider())

    missing_files = await service.find_missing_files("test_user", "test_submission", submission_files)
    assert missing_files == []
    admin_handler.get_user_files.assert_awaited_once_with("test_user", "test_submission")

    # File missing from inbox.
    admin_handler = get_mock_admin_handler([])
    submission_files = get_submission_files(["IMAGES/IMAGE_1/img1.dcm"])
    service = S3InboxSDAService(admin_handler, _mock_key_provider())

    missing_files = await service.find_missing_files("test_user", "test_submission", submission_files)
    assert missing_files == ["IMAGES/IMAGE_1/img1.dcm"]
    admin_handler.get_user_files.assert_awaited_once_with("test_user", "test_submission")


@pytest.mark.asyncio
async def test_find_orphaned_files():
    # No orphaned files.
    admin_handler = get_mock_admin_handler(["IMAGES/IMAGE_1/img1.dcm"])
    submission_files = get_submission_files(["IMAGES/IMAGE_1/img1.dcm"])
    service = S3InboxSDAService(admin_handler, _mock_key_provider())

    orphaned_files = await service.find_orphaned_files("test_user", "test_submission", submission_files)
    assert orphaned_files == []
    admin_handler.get_user_files.assert_awaited_once_with("test_user", "test_submission")

    # File missing from submission.
    admin_handler = get_mock_admin_handler(["IMAGES/IMAGE_1/img1.dcm"])
    submission_files = []
    service = S3InboxSDAService(admin_handler, _mock_key_provider())

    orphaned_files = await service.find_orphaned_files("test_user", "test_submission", submission_files)
    assert orphaned_files == ["IMAGES/IMAGE_1/img1.dcm"]
    admin_handler.get_user_files.assert_awaited_once_with("test_user", "test_submission")


async def test__find_missing_files():
    inbox_file_paths = {"file1.txt.c4gh"}
    file_paths = ["file1.txt.c4gh", "file2.txt.c4gh"]

    result = await S3InboxSDAService._find_missing_files(inbox_file_paths, file_paths)
    assert result == ["file2.txt.c4gh"]


async def test__find_orphaned_files():
    inbox_file_paths = ["file1.txt.c4gh", "file2.txt.c4gh"]
    file_paths = {"file2.txt.c4gh"}

    result = await S3InboxSDAService._find_orphaned_files(inbox_file_paths, file_paths)
    assert result == ["file1.txt.c4gh"]


@pytest.mark.asyncio
async def test_list_submission_inbox_files():
    admin_handler = AsyncMock()
    admin_handler.get_user_files.return_value = [
        FileItem(
            fileID="12345678-1234-4234-8234-1234567890ab",
            inboxPath="DATASET_1/LANDING_PAGE/THUMBNAILS/thumb.jpg",
            fileStatus="uploaded",
            createdAt="2024-01-01T00:00:00Z",
        )
    ]

    service = S3InboxSDAService(admin_handler, _mock_key_provider())

    inbox_files = await service.list_submission_inbox_files("user1", "1")

    assert [file.inbox_path for file in inbox_files] == ["DATASET_1/LANDING_PAGE/THUMBNAILS/thumb.jpg"]
    admin_handler.get_user_files.assert_awaited_once_with("user1", "1")
