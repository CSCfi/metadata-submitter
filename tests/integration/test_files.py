"""Test operations with files."""

import logging

from tests.integration.helpers import (
    add_submission_files,
    delete_project_files,
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
        mock_file_1 = generate_mock_file("test_delete_project_file_1")
        mock_file_2 = generate_mock_file("test_delete_project_file_2")
        mock_file_3 = generate_mock_file("test_delete_project_file_3")
        file_data = {
            "userId": user_data["userId"],
            "projectId": project_id,
            "files": [mock_file_1, mock_file_2, mock_file_3],
        }
        created_files = await post_project_files(client_logged_in, file_data)
        assert len(created_files) == 3

        # Confirm files exist inside project
        file_id_1 = created_files[0][0]
        file_id_2 = created_files[1][0]
        file_id_3 = created_files[2][0]
        file_1_exists = await find_project_file(client_logged_in, project_id, file_id_1)
        file_2_exists = await find_project_file(client_logged_in, project_id, file_id_2)
        file_3_exists = await find_project_file(client_logged_in, project_id, file_id_3)
        assert file_1_exists is True
        assert file_2_exists is True
        assert file_3_exists is True

        # Add files to a submission
        file_info = [
            {"accessionId": file_id_1, "version": created_files[0][1]},
            {"accessionId": file_id_2, "version": created_files[1][1]},
            {"accessionId": file_id_3, "version": created_files[2][1]},
        ]
        await add_submission_files(client_logged_in, file_info, submission_id)
        submission_info = await get_submission(client_logged_in, submission_id)
        assert len(submission_info["files"]) == 3

        # Query created files in database
        db_file_1 = await database["file"].find_one({"accessionId": file_id_1, "projectId": project_id})
        db_file_2 = await database["file"].find_one({"accessionId": file_id_2, "projectId": project_id})
        db_file_3 = await database["file"].find_one({"accessionId": file_id_3, "projectId": project_id})

        # Verify that all 3 files are not flagged as deleted
        assert db_file_1["flagDeleted"] is False
        assert db_file_2["flagDeleted"] is False
        assert db_file_3["flagDeleted"] is False

        # Flag 2 files as deleted in DB and remove 2 files from current submission
        await delete_project_files(client_logged_in, project_id, [mock_file_1["path"], mock_file_2["path"]])

        # Verify that 2 files were removed from current submission
        submission_info = await get_submission(client_logged_in, submission_id)
        assert len(submission_info["files"]) == 1

        # Verify that 2 files are flagged as deleted and not shown anymore in the list of project files
        project_files = await get_project_files(client_logged_in, project_id)
        assert len(project_files) == 1

        file_1_exists = await find_project_file(client_logged_in, project_id, file_id_1)
        file_2_exists = await find_project_file(client_logged_in, project_id, file_id_2)
        assert file_1_exists is False
        assert file_2_exists is False

        # Query flagged as deleted files in database
        db_file_1_deleted = await database["file"].find_one({"accessionId": file_id_1, "projectId": project_id})
        db_file_2_deleted = await database["file"].find_one({"accessionId": file_id_2, "projectId": project_id})
        db_file_3_deleted = await database["file"].find_one({"accessionId": file_id_3, "projectId": project_id})

        # Verify that 2 files are flagged as deleted, 1 file is kept as it is
        assert db_file_1_deleted["flagDeleted"] is True
        assert db_file_2_deleted["flagDeleted"] is True
        assert db_file_3_deleted["flagDeleted"] is False


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
