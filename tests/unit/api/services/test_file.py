import socket

import pytest

from aiohttp import web
from moto.server import ThreadedMotoServer

from metadata_backend.api.services.file import (
    S3FileService,
    S3_ACCESS_KEY_ENV,
    S3_SECRET_KEY_ENV,
    S3_REGION_ENV,
    S3_ENDPOINT_ENV
)

@pytest.fixture
def s3_endpoint(monkeypatch):
    # Create moto server.
    s = socket.socket()
    s.bind(('', 0))
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

    yield endpoint
    server.stop()


@pytest.mark.asyncio
async def test_verify_user_file_exists(s3_endpoint):
    service = S3FileService()
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
