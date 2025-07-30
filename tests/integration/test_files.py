"""Test operations with files."""

import logging
import re

from tests.integration.conftest import submission_factory
from tests.integration.helpers import (
    find_project_file,
    generate_mock_file,
    get_project_files,
    patch_submission_files,
    post_project_files,
    submissions_url,
    get_submission_files,
    delete_submission_file,
)

LOG = logging.getLogger(__name__)
LOG.setLevel(logging.DEBUG)


class TestFiles:
    """Test posting, getting, and deleting files."""

    async def test_post_project_file(self, client_logged_in, user_id, project_id):
        """Test file posting endpoint.

        :param client_logged_in: HTTP client in which request call is made
        :param user_id: User ID of the logged in user
        :param project_id: Project ID of the logged in user
        """

        # Post file and check its creation succeeded
        file_data = {
            "userId": user_id,
            "projectId": project_id,
            "files": [generate_mock_file("mock_file")],
        }

        created_files = await post_project_files(client_logged_in, file_data)
        LOG.debug("Created files: %s", created_files)
        assert len(created_files) == 1

        # Confirm file exists within project
        file_exists = await find_project_file(client_logged_in, project_id, created_files[0]["accessionId"])
        assert file_exists is True

    async def test_project_files(self, client_logged_in, user_id, project_id, project_id_2):
        """Test that files are properly posted and retrieved for multiple projects.

        :param client_logged_in: HTTP client in which request call is made
        :param user_id: User ID of the logged in user
        :param project_id: Project ID of the logged in user
        :param project_id_2: Second project ID of the logged in user
        """
        # Post files to one project and check that creation succeeded
        file_data = {
            "userId": user_id,
            "projectId": project_id,
            "files": [generate_mock_file("file_1"), generate_mock_file("file_2")],
        }
        created_files = await post_project_files(client_logged_in, file_data)
        LOG.debug("Created files: %s", created_files)
        assert len(created_files) == len(file_data["files"])

        file_data = {
            "userId": user_id,
            "projectId": project_id_2,
            "files": [generate_mock_file("file_3"), generate_mock_file("file_4")],
        }
        created_files = await post_project_files(client_logged_in, file_data)
        LOG.debug("Created files: %s", created_files)
        assert len(created_files) == len(file_data["files"])

        # Get files from all projects
        files: list[dict[str, any]] = []

        projects_ids = [project_id, project_id_2]

        for pro_id in projects_ids:
            project_files = await get_project_files(client_logged_in, pro_id)
            for file in project_files:
                files.append(file)
        assert len(files) == 4

        # Check that files have correct names and projects associated
        for index, file in enumerate(files):
            assert file["name"] == f"file_{index + 1}.c4gh"
            assert file["projectId"] == projects_ids[int(index / 2)]

    async def test_post_project_bigpicture_file(self, client_logged_in, user_id, project_id):
        """Test file posting to BP project has correct accessionId format.

        :param client_logged_in: HTTP client in which request call is made
        :param user_id: User ID of the logged in user
        :param project_id: Project ID of the logged in user
        """
        # Post BP file
        bp_file_data = {
            "userId": user_id,
            "projectId": project_id,
            "files": [generate_mock_file("bp_file")],
        }

        bp_files = await post_project_files(client_logged_in, bp_file_data, "true")
        assert len(bp_files) == 1

        # Confirm file exists within project
        file_exists = await find_project_file(client_logged_in, project_id, bp_files[0]["accessionId"])
        assert file_exists is True

        # Assert file's accession id has correct format for Bigpicture
        bp_file_id_pattern = re.compile("^bb-file(-[a-hj-knm-z23456789]{6}){2}$")
        assert bp_file_id_pattern.match(bp_files[0]["accessionId"]), "BP file id did not have correct format"

        # Post another normal file
        file_data = {
            "userId": user_id,
            "projectId": project_id,
            "files": [generate_mock_file("mock_file")],
        }

        files = await post_project_files(client_logged_in, file_data)
        assert len(files) == 1
        assert not bp_file_id_pattern.match(files[0]["accessionId"]), "Normal file id did not have correct format"

    async def test_add_get_delete_submission_file(self, client_logged_in, submission_factory, user_id, project_id):
        """Test adding, getting and deleting a file from submission.

        :param client_logged_in: HTTP client in which request call is made
        :param submission_factory: The factory that creates and deletes submissions
        """
        submission_id, _ = await submission_factory("SDSX")

        # Post 3 files
        mock_files = []
        for index in range(1, 4):
            mock_file = generate_mock_file(f"test_delete_project_file_{index}")
            mock_files.append(mock_file)

        file_data = {
            "userId": user_id,
            "projectId": project_id,
            "files": mock_files,
        }
        created_files = await post_project_files(client_logged_in, file_data)
        assert len(created_files) == 3

        # Confirm files exist inside project
        files_info = []
        for index, file in enumerate(created_files):
            file_exists = await find_project_file(client_logged_in, project_id, file["accessionId"])
            assert file_exists is True
            # Append file info as dict to a list
            files_info.append(
                {"accessionId": file["accessionId"], "version": file["version"], "path": mock_files[index]["path"]}
            )

        # Add files to a submission
        await patch_submission_files(client_logged_in, files_info, submission_id)

        # Test that the submission has three files
        submission_files = await get_submission_files(client_logged_in, submission_id)
        assert len(submission_files) == 3

        # Delete two files from the submission
        await delete_submission_file(client_logged_in, submission_id, submission_files[0]["fileId"])
        await delete_submission_file(client_logged_in, submission_id, submission_files[1]["fileId"])

        # Test that the submission has one file
        submission_files = await get_submission_files(client_logged_in, submission_id)
        assert len(submission_files) == 1


class TestFileSubmissions:
    """Test file operations in submissions."""

    async def test_add_delete_submission_files(self, client_logged_in, submission_factory, user_id, project_id):
        """Test that adding and updating files in a submission works.

        :param client_logged_in: HTTP client in which request call is made
        :param submission_factory: The factory that creates and deletes submissions
        :param user_id: User ID of the logged in user
        :param project_id: Project ID of the logged in user
        """
        submission_id, _ = await submission_factory("Bigpicture")

        async with client_logged_in.get(f"{submissions_url}/{submission_id}") as resp:
            LOG.debug("Checking that submission %s was created", submission_id)
            assert resp.status == 200, f"HTTP Status code error, got {resp.status}"

        # Post a file
        file_data = {
            "userId": user_id,
            "projectId": project_id,
            "files": [generate_mock_file("test_update_submission_file")],
        }
        created_files = await post_project_files(client_logged_in, file_data)
        assert len(created_files) == 1

        # Confirm file exists within project
        file_id = created_files[0]["accessionId"]
        file_exists = await find_project_file(client_logged_in, project_id, file_id)
        assert file_exists is True

        # Add file to a submission
        file_info = [{"accessionId": file_id, "version": created_files[0]["version"]}]
        await patch_submission_files(client_logged_in, file_info, submission_id)
        submission_files = await get_submission_files(client_logged_in, submission_id)
        assert len(submission_files) == 1

        # Delete file from submission
        await delete_submission_file(client_logged_in, submission_id, submission_files[0]["fileId"])
        submission_files = await get_submission_files(client_logged_in, submission_id)
        assert len(submission_files) == 0

    async def test_creating_file_version(self, client_logged_in, user_id, project_id):
        """Test creating a file version.

        :param client_logged_in: HTTP client in which request call is made
        :param user_id: User ID of the logged in user
        :param project_id: Project ID of the logged in user
        """
        # Post file and check its version number
        file_data = {
            "userId": user_id,
            "projectId": project_id,
            "files": [generate_mock_file("mock_file")],
        }
        posted_files = await post_project_files(client_logged_in, file_data)
        assert posted_files[0]["version"] == 1

        # Post same file and check that accession id is same, version is incremented
        posted_files2 = await post_project_files(client_logged_in, file_data)
        assert posted_files2[0]["version"] == 2
        assert posted_files2[0]["accessionId"] == posted_files[0]["accessionId"]

        # Create version 3
        posted_files3 = await post_project_files(client_logged_in, file_data)
        assert posted_files3[0]["version"] == 3

        # Get file. Only file's latest version is returned
        project_files = await get_project_files(client_logged_in, project_id)
        assert len(project_files) == 1
