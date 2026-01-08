"""Integration tests for S3 file provider service."""

import os
import uuid

import pytest
from aiohttp import web

from tests.integration.conf import mock_keystone_url


async def test_file_provider_service(client, secret_env, s3_manager, monkeypatch):
    """Test all methods of the FileProviderService using a test service."""
    monkeypatch.setenv("KEYSTONE_ENDPOINT", mock_keystone_url)
    from metadata_backend.api.services.file import S3AllasFileProviderService
    from metadata_backend.services.keystone_service import KeystoneServiceHandler

    test_user_creds = KeystoneServiceHandler.EC2Credentials(
        access=os.getenv("USER_S3_ACCESS_KEY_ID"),
        secret=os.getenv("USER_S3_SECRET_ACCESS_KEY"),
    )
    api_static_creds = KeystoneServiceHandler.EC2Credentials(
        access=os.getenv("STATIC_S3_ACCESS_KEY_ID"),
        secret=os.getenv("STATIC_S3_SECRET_ACCESS_KEY"),
    )

    service = S3AllasFileProviderService()

    test_bucket = f"test-bucket-{uuid.uuid4().hex[:8]}"
    test_file_1 = "test-file-1.txt"
    test_file_2 = "test-file-2.txt"

    try:
        # Verifying bucket policy should fail when bucket does not exist
        policy_exists = await service.verify_bucket_policy(test_bucket)
        assert policy_exists is False

        # Create new test bucket to user's project
        await s3_manager.add_bucket(test_bucket)

        # List buckets using the user credentials
        buckets = await service.list_buckets(test_user_creds)
        assert isinstance(buckets, list)
        assert test_bucket in buckets

        # API should NOT see the same bucket with static credentials (in another project)
        buckets = await service.list_buckets(api_static_creds)
        assert test_bucket not in buckets

        # Methods requiring read access policy should fail before policy is set
        policy_exists = await service.verify_bucket_policy(test_bucket)
        assert policy_exists is False

        with pytest.raises(web.HTTPBadRequest) as e:
            files = await service.list_files_in_bucket(test_bucket)
        assert str(e.value.reason) == f"Bucket '{test_bucket}' has not been made accessible to SD Submit."

        with pytest.raises(web.HTTPBadRequest) as e:
            await service.verify_user_file(test_bucket, test_file_1)
        assert str(e.value.reason) == f"Bucket '{test_bucket}' has not been made accessible to SD Submit."

        # Update bucket policy to grant read access
        await service.update_bucket_policy(test_bucket, test_user_creds)
        policy_exists = await service.verify_bucket_policy(test_bucket)
        assert policy_exists is True

        # List files before and after adding files to the bucket
        with pytest.raises(web.HTTPNotFound) as e:
            files = await service.list_files_in_bucket(test_bucket)
        assert str(e.value.reason) == f"No files found in bucket '{test_bucket}'."

        await s3_manager.add_file_to_bucket(test_bucket, test_file_1)
        await s3_manager.add_file_to_bucket(test_bucket, test_file_2)

        files = await service.list_files_in_bucket(test_bucket)
        assert isinstance(files.root, list)
        assert len(files.root) >= 2
        assert files.root[0].path.startswith(f"S3://{test_bucket}/{test_file_1}")
        assert files.root[1].path.startswith(f"S3://{test_bucket}/{test_file_2}")

        # Verify specific user files
        with pytest.raises(web.HTTPBadRequest) as exc_info:
            await service.verify_user_file(test_bucket, "nonexistent.txt")
        assert str(exc_info.value.reason) == f"File 'nonexistent.txt' does not exist in bucket '{test_bucket}'."

        verified_size = await service.verify_user_file(test_bucket, test_file_1)
        assert verified_size == 100

    finally:
        # Cleanup - remove the test bucket
        await s3_manager.delete_bucket(test_bucket)
        buckets = await service.list_buckets(test_user_creds)
        assert test_bucket not in buckets
