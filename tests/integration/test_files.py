"""Test operations with files."""

import logging

from tests.integration.conf import files_url

LOG = logging.getLogger(__name__)
LOG.setLevel(logging.DEBUG)


class TestFiles:
    """Test fetching files from S3 API."""

    async def test_list_folders(self, client_logged_in, project_id, s3_manager):
        """Test listing folders in a project."""
        response = await client_logged_in.get(f"{files_url}/{project_id}/folders")
        assert response.status == 400
        resp = await response.json()
        assert resp["detail"] == "No folders found."

        await s3_manager.add_folder("folder1")
        await s3_manager.add_folder("folder2")
        response = await client_logged_in.get(f"{files_url}/{project_id}/folders")
        assert response.status == 200
        folders = await response.json()
        assert isinstance(folders, list)
        assert set(folders) == {"folder1", "folder2"}

        await s3_manager.add_folder("folder3")
        response = await client_logged_in.get(f"{files_url}/{project_id}/folders")
        assert response.status == 200
        folders = await response.json()
        assert "folder3" in folders

    async def test_list_files_in_folder(self, client_logged_in, project_id, s3_manager):
        """Test listing files in a specific folder."""
        folder_name = "folder1"
        response = await client_logged_in.get(f"{files_url}/{project_id}/folders/{folder_name}/files")
        assert response.status == 400
        resp = await response.json()
        assert resp["detail"] == "The specified bucket does not exist."

        await s3_manager.add_folder(folder_name)
        await s3_manager.add_file_to_folder(folder_name, "file1.txt")
        await s3_manager.add_file_to_folder(folder_name, "file2.txt")
        response = await client_logged_in.get(f"{files_url}/{project_id}/folders/{folder_name}/files")
        assert response.status == 200
        files = await response.json()
        assert isinstance(files, list)
        assert files[0]["path"] == f"S3://{folder_name}/file1.txt"
        assert files[0]["bytes"] == 100
        assert files[1]["path"] == f"S3://{folder_name}/file2.txt"
