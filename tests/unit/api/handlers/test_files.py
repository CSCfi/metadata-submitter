"""Test API endpoints from FilesAPIHandler."""

from unittest.mock import patch

from metadata_backend.api.services.file import FileProviderService
from metadata_backend.conf.conf import API_PREFIX

from .common import HandlersTestCase


class FilesAPIHandlerTestCase(HandlersTestCase):
    """Files API handler test cases."""

    async def asyncSetUp(self) -> None:
        """Set up async test fixtures."""
        await super().asyncSetUp()
        self.patch_fetch_project_token = patch(
            "metadata_backend.services.pouta_service_handler.KeystoneService.fetch_project_token",
            return_value={},
        )
        self.patch_get_ec2 = patch(
            "metadata_backend.services.pouta_service_handler.KeystoneService.get_ec2_for_project",
            return_value={},
        )
        self.patch_delete_ec2 = patch(
            "metadata_backend.services.pouta_service_handler.KeystoneService.delete_ec2_from_project",
            return_value=204,
        )

    async def test_get_project_buckets(self) -> None:
        """Test getting project buckets."""

        project_id = "PRJ123"

        with (
            self.patch_verify_authorization,
            self.patch_verify_user_project,
            self.patch_fetch_project_token,
            self.patch_get_ec2,
            self.patch_delete_ec2,
            patch(
                "metadata_backend.api.services.file.FileProviderService.list_buckets",
                return_value=["bucket1", "bucket2"],
            ),
        ):
            response = await self.client.get(f"{API_PREFIX}/projects/{project_id}/buckets")
            self.assertEqual(response.status, 200)

            buckets = await response.json()
            assert len(buckets) == 2
            assert "bucket1" and "bucket2" in buckets

    async def test_get_files_in_bucket(self) -> None:
        """Test getting files in a bucket."""

        project_id = "PRJ123"
        bucket_name = "bucket1"
        file1 = FileProviderService.File(path="S3://bucket1/file1.txt", bytes=100)
        file2 = FileProviderService.File(path="S3://bucket1/file2.txt", bytes=101)

        with (
            self.patch_verify_authorization,
            self.patch_verify_user_project,
            patch(
                "metadata_backend.api.services.file.S3AllasFileProviderService._verify_bucket_policy",
                return_value=False,
            ),
        ):
            response = await self.client.get(f"{API_PREFIX}/projects/{project_id}/buckets/{bucket_name}/files")
            self.assertEqual(response.status, 400)

        with (
            self.patch_verify_authorization,
            self.patch_verify_user_project,
            patch(
                "metadata_backend.api.services.file.FileProviderService.list_files_in_bucket",
                return_value=FileProviderService.Files([file1, file2]),
            ),
        ):
            response = await self.client.get(f"{API_PREFIX}/projects/{project_id}/buckets/{bucket_name}/files")
            self.assertEqual(response.status, 200)

            files = await response.json()
            assert len(files) == 2
            assert files[1]["path"] == "S3://bucket1/file2.txt"
            assert files[1]["bytes"] == 101

    async def test_grant_access_to_bucket(self) -> None:
        """Test granting access to a bucket."""

        project_id = "PRJ123"
        bucket_name = "bucket1"

        with (
            self.patch_verify_authorization,
            self.patch_verify_user_project,
            self.patch_fetch_project_token,
            self.patch_get_ec2,
            self.patch_delete_ec2,
            patch(
                "metadata_backend.api.services.file.FileProviderService.update_bucket_policy",
                return_value=None,
            ),
        ):
            response = await self.client.put(f"{API_PREFIX}/projects/{project_id}/buckets/{bucket_name}")
            self.assertEqual(response.status, 200)

    async def test_check_bucket_access(self) -> None:
        """Test checking access to a bucket."""

        project_id = "PRJ123"
        bucket_name = "bucket1"

        with (
            self.patch_verify_authorization,
            self.patch_verify_user_project,
            patch(
                "metadata_backend.api.services.file.FileProviderService.verify_bucket_policy",
                return_value=True,
            ),
        ):
            response = await self.client.head(f"{API_PREFIX}/projects/{project_id}/buckets/{bucket_name}")
            self.assertEqual(response.status, 200)

        with (
            self.patch_verify_authorization,
            self.patch_verify_user_project,
            patch(
                "metadata_backend.api.services.file.FileProviderService.verify_bucket_policy",
                return_value=False,
            ),
        ):
            response = await self.client.head(f"{API_PREFIX}/projects/{project_id}/buckets/{bucket_name}")
            self.assertEqual(response.status, 400)
