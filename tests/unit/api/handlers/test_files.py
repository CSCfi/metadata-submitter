"""Test API endpoints from FilesAPIHandler."""

from unittest.mock import patch

from metadata_backend.api.services.file import FileProviderService
from metadata_backend.conf.conf import API_PREFIX
from tests.unit.patches.keystone_service import (
    patch_keystone_delete_ec2,
    patch_keystone_get_ec2,
    patch_keystone_get_project_entry,
)
from tests.unit.patches.user import patch_verify_authorization, patch_verify_user_project


async def test_get_project_buckets(csc_client) -> None:
    """Test getting project buckets."""

    project_id = "PRJ123"

    with (
        patch_verify_authorization,
        patch_verify_user_project,
        patch_keystone_get_project_entry,
        patch_keystone_get_ec2,
        patch_keystone_delete_ec2,
        patch(
            "metadata_backend.api.services.file.FileProviderService.list_buckets",
            return_value=["bucket1", "bucket2"],
        ),
    ):
        response = csc_client.get(f"{API_PREFIX}/buckets?projectId={project_id}")
        assert response.status_code == 200

        buckets = response.json()
        assert len(buckets) == 2
        assert "bucket1" and "bucket2" in buckets


async def test_get_files_in_bucket(csc_client) -> None:
    """Test getting files in a bucket."""

    project_id = "PRJ123"
    bucket_name = "bucket1"
    file1 = FileProviderService.File(path="S3://bucket1/file1.txt", bytes=100)
    file2 = FileProviderService.File(path="S3://bucket1/file2.txt", bytes=101)

    with (
        patch_verify_authorization,
        patch_verify_user_project,
        patch(
            "metadata_backend.api.services.file.S3AllasFileProviderService._verify_bucket_policy",
            return_value=False,
        ),
    ):
        response = csc_client.get(f"{API_PREFIX}/buckets/{bucket_name}/files?projectId={project_id}")
        assert response.status_code == 400

    with (
        patch_verify_authorization,
        patch_verify_user_project,
        patch(
            "metadata_backend.api.services.file.FileProviderService.list_files_in_bucket",
            return_value=FileProviderService.Files([file1, file2]),
        ),
    ):
        response = csc_client.get(f"{API_PREFIX}/buckets/{bucket_name}/files?projectId={project_id}")
        assert response.status_code == 200

        files = response.json()
        assert len(files) == 2
        assert files[1]["path"] == "S3://bucket1/file2.txt"
        assert files[1]["bytes"] == 101


async def test_grant_access_to_bucket(csc_client) -> None:
    """Test granting access to a bucket."""

    project_id = "PRJ123"
    bucket_name = "bucket1"

    with (
        patch_verify_authorization,
        patch_verify_user_project,
        patch_keystone_get_project_entry,
        patch_keystone_get_ec2,
        patch_keystone_delete_ec2,
        patch(
            "metadata_backend.api.services.file.FileProviderService.update_bucket_policy",
            return_value=None,
        ),
    ):
        response = csc_client.put(f"{API_PREFIX}/buckets/{bucket_name}?projectId={project_id}")
        assert response.status_code == 200


async def test_check_bucket_access(csc_client) -> None:
    """Test checking access to a bucket."""

    project_id = "PRJ123"
    bucket_name = "bucket1"

    with (
        patch_verify_authorization,
        patch_verify_user_project,
        patch(
            "metadata_backend.api.services.file.FileProviderService.verify_bucket_policy",
            return_value=True,
        ),
    ):
        response = csc_client.head(f"{API_PREFIX}/buckets/{bucket_name}?projectId={project_id}")
        assert response.status_code == 200

    with (
        patch_verify_authorization,
        patch_verify_user_project,
        patch(
            "metadata_backend.api.services.file.FileProviderService.verify_bucket_policy",
            return_value=False,
        ),
    ):
        response = csc_client.head(f"{API_PREFIX}/buckets/{bucket_name}?projectId={project_id}")
        assert response.status_code == 400
