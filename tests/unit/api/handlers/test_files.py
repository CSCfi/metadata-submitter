"""Test API endpoints from FilesAPIHandler."""

from unittest.mock import patch

from metadata_backend.api.services.file import FileProviderService
from metadata_backend.conf.conf import API_PREFIX

from .common import HandlersTestCase


class FilesAPIHandlerTestCase(HandlersTestCase):
    """Files API handler test cases."""

    async def test_get_project_folders(self) -> None:
        """Test getting project folders."""

        project_id = "PRJ123"

        with (
            self.patch_verify_authorization,
            self.patch_verify_user_project,
            patch(
                "metadata_backend.api.services.file.FileProviderService.list_folders",
                return_value=["folder1", "folder2"],
            ),
        ):
            response = await self.client.get(f"{API_PREFIX}/projects/{project_id}/folders")
            self.assertEqual(response.status, 200)

            folders = await response.json()
            assert len(folders) == 2
            assert "folder1" and "folder2" in folders

    async def test_get_files_in_folder(self) -> None:
        """Test getting files in a folder."""

        project_id = "PRJ123"
        folder_name = "folder1"
        file1 = FileProviderService.File(path="S3://folder1/file1.txt", bytes=100)
        file2 = FileProviderService.File(path="S3://folder1/file2.txt", bytes=101)

        with (
            self.patch_verify_authorization,
            self.patch_verify_user_project,
            patch(
                "metadata_backend.api.services.file.FileProviderService.list_files_in_folder",
                return_value=FileProviderService.Files([file1, file2]),
            ),
        ):
            response = await self.client.get(f"{API_PREFIX}/projects/{project_id}/folders/{folder_name}/files")
            self.assertEqual(response.status, 200)

            files = await response.json()
            assert len(files) == 2
            assert files[1]["path"] == "S3://folder1/file2.txt"
            assert files[1]["bytes"] == 101
