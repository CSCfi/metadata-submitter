import socket

import pytest
from aiobotocore import session
from aiohttp import web
from moto.server import ThreadedMotoServer

from metadata_backend.api.services.file import (
    S3_ACCESS_KEY_ENV,
    S3_ENDPOINT_ENV,
    S3_REGION_ENV,
    S3_SECRET_KEY_ENV,
    S3FileProviderService,
)


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

    # Set environment variables.
    monkeypatch.setenv(S3_ACCESS_KEY_ENV, "test")
    monkeypatch.setenv(S3_SECRET_KEY_ENV, "test")
    monkeypatch.setenv(S3_REGION_ENV, "us-east-1")
    monkeypatch.setenv(S3_ENDPOINT_ENV, endpoint)

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
    service = S3FileProviderService()
    session = service._session

    bucket = "test-bucket"
    file = "test-file"
    content = b"test"

    # Bucket and file does not exist.
    size = await service._verify_user_file(bucket, file)
    assert size is None
    with pytest.raises(web.HTTPBadRequest):
        await service.verify_user_file(bucket, file)

    async with session.client("s3", endpoint_url=s3_endpoint) as s3:
        # Create bucket.
        await s3.create_bucket(Bucket=bucket)

        # File does not exist.
        size = await service._verify_user_file(bucket, file)
        assert size is None
        with pytest.raises(web.HTTPBadRequest):
            await service.verify_user_file(bucket, file)

        # Create file.
        await s3.put_object(Bucket=bucket, Key=file, Body=content)

        # File exists.
        size = await service._verify_user_file(bucket, file)
        assert size == len(content)

        size = await service.verify_user_file(bucket, file)
        assert size == len(content)


@pytest.mark.asyncio
async def test_list_buckets_and_files(s3_endpoint):
    service = S3FileProviderService()
    session = service._session

    bucket = "test-bucket"
    file = "test-file"
    content = b"test"

    async with session.client("s3", endpoint_url=s3_endpoint) as s3:
        # No buckets yet
        with pytest.raises(web.HTTPBadRequest):
            await service.list_buckets()

        # Create bucket
        await s3.create_bucket(Bucket=bucket)

        # Now list_buckets should return one bucket
        buckets = await service.list_buckets()
        assert buckets[0] == bucket

        # No files in bucket yet
        with pytest.raises(web.HTTPBadRequest):
            await service.list_files_in_bucket(bucket)

        # Add a file
        await s3.put_object(Bucket=bucket, Key=file, Body=content)

        # Now list_files_in_bucket should return the file
        files = await service.list_files_in_bucket(bucket)
        assert files.root[0].path == f"S3://{bucket}/{file}"
        assert files.root[0].bytes == len(content)
