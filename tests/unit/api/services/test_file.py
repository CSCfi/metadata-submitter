import socket

import pytest
import ujson
from aiobotocore import session
from moto.server import ThreadedMotoServer

from metadata_backend.api.exceptions import UserException
from metadata_backend.api.services.file import S3AllasFileProviderService
from metadata_backend.conf.s3 import s3_config
from metadata_backend.services.keystone_service import KeystoneServiceHandler

bucket = "test-bucket"
file = "test-file"
content = b"test"
creds = KeystoneServiceHandler.EC2Credentials(access="test-id", secret="test-key")


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

        # No files in bucket yet
        await service.update_bucket_policy(bucket, creds)
        with pytest.raises(UserException):
            await service.list_files_in_bucket(bucket)

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
