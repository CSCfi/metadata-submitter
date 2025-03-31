"""Test operations with files."""

import logging
import re

from tests.integration.helpers import (
    delete_project_files,
    find_project_file,
    generate_mock_file,
    get_project_files,
    get_submission,
    get_user_data,
    patch_submission_files,
    post_project_files,
    post_submission,
    remove_submission_file,
    submissions_url,
)

LOG = logging.getLogger(__name__)
LOG.setLevel(logging.DEBUG)


class TestFiles:
    """Test posting, getting, and deleting files."""

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
        LOG.debug("Created files: %s", created_files)
        assert len(created_files) == 1

        # Confirm file exists within project
        file_exists = await find_project_file(client_logged_in, projectId, created_files[0]["accessionId"])
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
        LOG.debug("Created files: %s", created_files)
        assert len(created_files) == len(file_data["files"])

        # Post files to another project
        project_id = user_data["projects"][1]["projectId"]

        file_data = {
            "userId": user_data["userId"],
            "projectId": project_id,
            "files": [generate_mock_file("file_3"), generate_mock_file("file_4")],
        }
        created_files = await post_project_files(client_logged_in, file_data)
        LOG.debug("Created files: %s", created_files)
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

    async def test_post_project_bigpicture_file(self, client_logged_in):
        """Test file posting to BP project has correct accessionId format.

        :param client_logged_in: HTTP client in which request call is made
        """
        # Get user data: userId and projects
        user_data = await get_user_data(client_logged_in)
        projectId = user_data["projects"][0]["projectId"]

        # Post BP file
        bp_file_data = {
            "userId": user_data["userId"],
            "projectId": projectId,
            "files": [generate_mock_file("bp_file")],
        }

        bp_files = await post_project_files(client_logged_in, bp_file_data, "true")
        assert len(bp_files) == 1

        # Confirm file exists within project
        file_exists = await find_project_file(client_logged_in, projectId, bp_files[0]["accessionId"])
        assert file_exists is True

        # Assert file's accession id has correct format for Bigpicture
        bp_file_id_pattern = re.compile("^bb-file(-[a-hj-knm-z23456789]{6}){2}$")
        assert bp_file_id_pattern.match(bp_files[0]["accessionId"]), "BP file id did not have correct format"

        # Post another normal file
        file_data = {
            "userId": user_data["userId"],
            "projectId": projectId,
            "files": [generate_mock_file("mock_file")],
        }

        files = await post_project_files(client_logged_in, file_data)
        assert len(files) == 1
        assert not bp_file_id_pattern.match(files[0]["accessionId"]), "Normal file id did not have correct format"

    async def test_delete_project_files(self, client_logged_in, database):
        """Test that specific file is flagged as deleted and removed from current submissions (not published).

        :param client_logged_in: HTTP client in which request call is made
        """
        # Get user data: user id and projects
        user_data = await get_user_data(client_logged_in)
        project_id = user_data["projects"][0]["projectId"]

        # Create a new submission and check its creation succeeded
        submission_data = {
            "name": "Test submission",
            "description": "Test submission with file to be deleted",
            "projectId": project_id,
            "workflow": "SDSX",
        }
        submission_id = await post_submission(client_logged_in, submission_data)

        # Post 3 files
        mock_files = []
        for index in range(1, 4):
            mock_file = generate_mock_file(f"test_delete_project_file_{index}")
            mock_files.append(mock_file)

        file_data = {
            "userId": user_data["userId"],
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
        submission_info = await get_submission(client_logged_in, submission_id)
        assert len(submission_info["files"]) == 3

        # Query created files in database. Verify that all 3 files are not flagged as deleted
        for file in files_info:
            db_file = await database["file"].find_one({"accessionId": file["accessionId"], "projectId": project_id})
            assert db_file["flagDeleted"] is False

        # Flag 2 files as deleted in DB and remove 2 files from current submission
        await delete_project_files(client_logged_in, project_id, [files_info[0]["path"], files_info[1]["path"]])

        # Verify that 2 files were removed from current submission
        submission_info = await get_submission(client_logged_in, submission_id)
        assert len(submission_info["files"]) == 1

        # Verify that 2 files are flagged as deleted and not shown anymore in the list of project files
        project_files = await get_project_files(client_logged_in, project_id)
        assert len(project_files) == 1
        for index in range(2):
            file_exists = await find_project_file(client_logged_in, project_id, files_info[index]["accessionId"])
            assert file_exists is False

        # Query flagged as deleted files in database. Verify that 2 files are flagged as deleted, 1 is kept as it is
        for index, file in enumerate(files_info):
            db_file_deleted = await database["file"].find_one(
                {"accessionId": file["accessionId"], "projectId": project_id}
            )
            if index == 2:
                assert db_file_deleted["flagDeleted"] is False
            else:
                assert db_file_deleted["flagDeleted"] is True


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
            LOG.debug("Checking that submission %s was created", submission_id)
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
        file_id = created_files[0]["accessionId"]
        file_exists = await find_project_file(client_logged_in, project_id, file_id)
        assert file_exists is True

        # Add file to a submission and verify
        file_info = [{"accessionId": file_id, "version": created_files[0]["version"]}]
        await patch_submission_files(client_logged_in, file_info, submission_id)
        submission_info = await get_submission(client_logged_in, submission_id)
        assert submission_info["files"][0]["accessionId"] == file_info[0]["accessionId"]
        assert submission_info["files"][0]["status"] == "added"

        # Update submission file status
        updated_file_info = [{**file_info[0], "status": "ready"}]
        await patch_submission_files(client_logged_in, updated_file_info, submission_id)

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
            LOG.debug("Checking that submission %s was created", submission_id)
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
            {"accessionId": created_files[0]["accessionId"], "version": created_files[0]["version"]},
            {"accessionId": created_files[1]["accessionId"], "version": created_files[1]["version"]},
        ]
        await patch_submission_files(client_logged_in, file_info, submission_id)

        # Verify that files were added
        submission_info = await get_submission(client_logged_in, submission_id)
        assert len(submission_info["files"]) == 2

        # Remove a file from submission
        await remove_submission_file(client_logged_in, submission_id, created_files[0]["accessionId"])

        # Verify that file was removed
        submission_info = await get_submission(client_logged_in, submission_id)
        assert len(submission_info["files"]) == 1
        assert submission_info["files"][0]["accessionId"] == created_files[1]["accessionId"]

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
        project_files = await get_project_files(client_logged_in, projectId)
        assert len(project_files) == 1
