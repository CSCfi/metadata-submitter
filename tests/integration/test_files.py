"""Test operations with files."""

import logging

from tests.integration.helpers import (
    add_submission_files,
    find_project_file,
    generate_mock_file,
    get_project_files,
    get_submission,
    get_user_data,
    post_project_files,
    post_submission,
    remove_submission_file,
    submissions_url,
    update_submission_files,
)

LOG = logging.getLogger(__name__)
LOG.setLevel(logging.DEBUG)


class TestFiles:
    """Test posting and getting files."""

    async def test_post_project_file(self, client_logged_in):
        """Test file posting endpoint.

        :param client_logged_in: HTTP client in which request call is made
        """
        # Get user data: userId and projects
        user_data = await get_user_data(client_logged_in)
        projectId = user_data["projects"][0]["projectId"]

        # Post file and check its creation succeeded
        file_data = {
            "userId": user_data["userId"],
            "projectId": projectId,
            "files": [generate_mock_file("mock_file")],
        }

        created_files = await post_project_files(client_logged_in, file_data)
        LOG.debug(f"Created files: {created_files}")
        assert len(created_files) == 1

        # Confirm file exists within project
        file_exists = await find_project_file(client_logged_in, projectId, created_files[0][0])
        assert file_exists is True

    async def test_project_files(self, client_logged_in):
        """Test that files are properly posted and retrieved for multiple projects.

        :param client_logged_in: HTTP client in which request call is made
        """
        # Get user data: userId and projects
        user_data = await get_user_data(client_logged_in)
        project_id = user_data["projects"][0]["projectId"]

        # Post files to one project and check that creation succeeded
        file_data = {
            "userId": user_data["userId"],
            "projectId": project_id,
            "files": [generate_mock_file("file_1"), generate_mock_file("file_2")],
        }
        created_files = await post_project_files(client_logged_in, file_data)
        LOG.debug(f"Created files: {created_files}")
        assert len(created_files) == len(file_data["files"])

        # Post files to another project
        project_id = user_data["projects"][1]["projectId"]

        file_data = {
            "userId": user_data["userId"],
            "projectId": project_id,
            "files": [generate_mock_file("file_3"), generate_mock_file("file_4")],
        }
        created_files = await post_project_files(client_logged_in, file_data)
        LOG.debug(f"Created files: {created_files}")
        assert len(created_files) == len(file_data["files"])

        # Get files from all projects
        files: list[dict[str, any]] = []

        for project in user_data["projects"]:
            project_files = await get_project_files(client_logged_in, project["projectId"])
            for file in project_files:
                files.append(file)
        assert len(files) == 4

        # Check that files have correct names and projects associated
        for index, file in enumerate(files):
            assert file["name"] == f"file_{index + 1}.c4gh"
            assert file["projectId"] == user_data["projects"][int(index / 2)]["projectId"]


class TestFileSubmissions:
    """Test file operations in submissions."""

    async def test_updating_submission_files(self, client_logged_in):
        """Test that adding and updating files in a submission works.

        :param client_logged_in: HTTP client in which request call is made
        """
        # Get user data: user id and projects
        user_data = await get_user_data(client_logged_in)
        project_id = user_data["projects"][0]["projectId"]

        # Create a new submission and check its creation succeeded
        submission_data = {
            "name": "Test submission",
            "description": "Test submission with file updating",
            "projectId": project_id,
            "workflow": "BigPicture",
        }
        submission_id = await post_submission(client_logged_in, submission_data)
        async with client_logged_in.get(f"{submissions_url}/{submission_id}") as resp:
            LOG.debug(f"Checking that submission {submission_id} was created")
            assert resp.status == 200, f"HTTP Status code error, got {resp.status}"

        # Post a file
        file_data = {
            "userId": user_data["userId"],
            "projectId": project_id,
            "files": [generate_mock_file("test_update_submission_file")],
        }
        created_files = await post_project_files(client_logged_in, file_data)
        assert len(created_files) == 1

        # Confirm file exists within project
        file_id = created_files[0][0]
        file_exists = await find_project_file(client_logged_in, project_id, file_id)
        assert file_exists is True

        # Add file to a submission and verify
        file_info = [{"accessionId": file_id, "version": created_files[0][1]}]
        await add_submission_files(client_logged_in, file_info, submission_id)
        submission_info = await get_submission(client_logged_in, submission_id)
        assert submission_info["files"][0]["accessionId"] == file_info[0]["accessionId"]
        assert submission_info["files"][0]["status"] == "added"

        # Update submission file status
        updated_file_info = [{**file_info[0], "status": "ready"}]
        await update_submission_files(client_logged_in, submission_id, updated_file_info)

        # Get submission
        submission_info = await get_submission(client_logged_in, submission_id)
        assert len(submission_info["files"]) == 1
        assert submission_info["files"][0]["status"] == updated_file_info[0]["status"]

    async def test_removing_submission_files(self, client_logged_in):
        """Test that adding and removing files in a submission works.

        :param client_logged_in: HTTP client in which request call is made
        """
        # Get user data: user id and projects
        user_data = await get_user_data(client_logged_in)
        project_id = user_data["projects"][0]["projectId"]

        # Create a new submission and check its creation succeeded
        submission_data = {
            "name": "Test submission",
            "description": "Test submission with file removal",
            "projectId": project_id,
            "workflow": "FEGA",
        }
        submission_id = await post_submission(client_logged_in, submission_data)
        async with client_logged_in.get(f"{submissions_url}/{submission_id}") as resp:
            LOG.debug(f"Checking that submission {submission_id} was created")
            assert resp.status == 200, f"HTTP Status code error, got {resp.status}"

        # Post files
        file_data = {
            "userId": user_data["userId"],
            "projectId": project_id,
            "files": [generate_mock_file("test_remove_file_1"), generate_mock_file("test_remove_file_2")],
        }
        created_files = await post_project_files(client_logged_in, file_data)
        assert len(created_files) == 2

        # Add files to submission
        file_info = [
            {"accessionId": created_files[0][0], "version": created_files[0][1]},
            {"accessionId": created_files[1][0], "version": created_files[1][1]},
        ]
        await add_submission_files(client_logged_in, file_info, submission_id)

        # Verify that files were added
        submission_info = await get_submission(client_logged_in, submission_id)
        assert len(submission_info["files"]) == 2

        # Remove a file from submission
        await remove_submission_file(client_logged_in, submission_id, created_files[0][0])

        # Verify that file was removed
        submission_info = await get_submission(client_logged_in, submission_id)
        assert len(submission_info["files"]) == 1
        assert submission_info["files"][0]["accessionId"] == created_files[1][0]

    async def test_creating_file_version(self, client_logged_in):
        """Test creating a file version.

        :param client_logged_in: HTTP client in which request call is made
        """
        # Get user data: userId and projects
        user_data = await get_user_data(client_logged_in)
        projectId = user_data["projects"][0]["projectId"]

        # Post file and check its version number
        file_data = {
            "userId": user_data["userId"],
            "projectId": projectId,
            "files": [generate_mock_file("mock_file")],
        }
        [(id, version)] = await post_project_files(client_logged_in, file_data)
        assert version == 1

        # Post same file and check that accession id is same, version is incremented
        [(id2, version2)] = await post_project_files(client_logged_in, file_data)
        assert version2 == 2
        assert id == id2

        # Get files
        project_files = await get_project_files(client_logged_in, projectId)
        assert len(project_files) == 2
