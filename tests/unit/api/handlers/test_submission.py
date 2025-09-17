"""Test API endpoints from SubmissionAPIHandler."""

import re
import uuid
from datetime import datetime, timedelta
from typing import Any

import ujson

from metadata_backend.conf.conf import API_PREFIX

from .common import HandlersTestCase


class SubmissionHandlerTestCase(HandlersTestCase):
    """Submission API endpoint class test cases."""

    async def test_post_get_delete_submission(self):
        """Test that submission post and get works."""

        # Test valid submission.

        name = f"name_{uuid.uuid4()}"
        description = f"description_{uuid.uuid4()}"
        project_id = f"project_{uuid.uuid4()}"
        workflow = "SDSX"

        # Post submission.

        submission_id = await self.post_submission(
            name=name, description=description, project_id=project_id, workflow=workflow
        )

        # Get submission.

        submission = await self.get_submission(submission_id)

        assert submission["name"] == name
        assert submission["description"] == description
        assert submission["projectId"] == project_id
        assert submission["workflow"] == workflow

        # Delete submission.

        with (
            self.patch_verify_user_project,
            self.patch_verify_authorization,
        ):
            response = await self.client.delete(f"{API_PREFIX}/submissions/{submission_id}")
            self.assertEqual(response.status, 204)

        # Get submission.

        with (
            self.patch_verify_user_project,
            self.patch_verify_authorization,
        ):
            response = await self.client.get(f"{API_PREFIX}/submissions/{submission_id}")
            self.assertEqual(response.status, 404)

    async def test_post_submission_fails_with_missing_fields(self):
        """Test that submission creation fails with missing fields."""

        data = {
            "name": f"name_{uuid.uuid4()}",
            "title": f"title_{uuid.uuid4()}",
            "description": f"description_{uuid.uuid4()}",
            "projectId": f"project_{uuid.uuid4()}",
            "workflow": "SDSX",
        }

        async def assert_missing_field(field: str):
            _data = {k: v for k, v in data.items() if k != field}
            with self.patch_verify_authorization:
                response = await self.client.post(f"{API_PREFIX}/submissions", json=_data)
                assert response.status == 400
                result = await response.json()
                assert f"'{field}' is a required property" in result["detail"]

        await assert_missing_field("name")
        await assert_missing_field("description")
        await assert_missing_field("projectId")
        await assert_missing_field("workflow")

    async def test_post_submission_fails_with_empty_body(self):
        """Test that submission creation fails when no data in request."""
        with self.patch_verify_authorization:
            response = await self.client.post(f"{API_PREFIX}/submissions")
            json_resp = await response.json()
            self.assertEqual(response.status, 400)
            self.assertIn("JSON is not correctly formatted", json_resp["detail"])

    async def test_post_submission_fails_with_duplicate_name(self):
        """Test that submission creation fails if the submission name already exists in the project."""
        name = f"name_{uuid.uuid4()}"
        project_id = f"project_{uuid.uuid4()}"

        await self.post_submission(name=name, project_id=project_id)

        data = {
            "name": name,
            "title": f"title_{uuid.uuid4()}",
            "description": f"description_{uuid.uuid4()}",
            "projectId": project_id,
            "workflow": "SDSX",
        }

        with (
            self.patch_verify_user_project,
            self.patch_verify_authorization,
        ):
            response = await self.client.post(f"{API_PREFIX}/submissions", json=data)
            json_resp = await response.json()
            self.assertEqual(response.status, 400)
            self.assertEqual(
                f"Submission with name '{name}' already exists in project {project_id}", json_resp["detail"]
            )

    async def test_get_submissions(self):
        """Test that get submissions works."""

        name_1 = f"name_{uuid.uuid4()}"
        name_2 = f"name_{uuid.uuid4()}"
        project_id = f"project_{uuid.uuid4()}"
        title = f"title_{uuid.uuid4()}"
        description = f"description_{uuid.uuid4()}"
        workflow = "SDSX"

        submission_id_1 = await self.post_submission(
            name=name_1, title=title, description=description, project_id=project_id, workflow=workflow
        )
        submission_id_2 = await self.post_submission(
            name=name_2, title=title, description=description, project_id=project_id, workflow=workflow
        )

        with (
            self.patch_verify_user_project,
            self.patch_verify_authorization,
        ):
            response = await self.client.get(f"{API_PREFIX}/submissions?projectId={project_id}")
            self.assertEqual(response.status, 200)
            result = await response.json()

            def _get_submission(submission_id: str) -> dict[str, Any] | None:
                for submission in result["submissions"]:
                    if submission["submissionId"] == submission_id:
                        return submission

                return None

            assert result["page"] == {
                "page": 1,
                "size": 5,
                "totalPages": 1,
                "totalSubmissions": 2,
            }
            assert len(result["submissions"]) == 2
            assert {
                       "dateCreated": _get_submission(submission_id_1)["dateCreated"],
                       "title": title,
                       "description": description,
                       "lastModified": _get_submission(submission_id_1)["lastModified"],
                       "name": name_1,
                       "projectId": project_id,
                       "published": False,
                       "submissionId": submission_id_1,
                       "text_name": " ".join(re.split("[\\W_]", name_1)),
                       "workflow": workflow,
                   } in result["submissions"]
            assert {
                       "dateCreated": _get_submission(submission_id_2)["dateCreated"],
                       "title": title,
                       "description": description,
                       "lastModified": _get_submission(submission_id_2)["lastModified"],
                       "name": name_2,
                       "projectId": project_id,
                       "published": False,
                       "submissionId": submission_id_2,
                       "text_name": " ".join(re.split("[\\W_]", name_2)),
                       "workflow": workflow,
                   } in result["submissions"]

    async def test_get_submissions_by_name(self):
        """Test that get submissions by name works."""

        name_1 = f"name_{uuid.uuid4()}"
        name_2 = f"{uuid.uuid4()}"
        name_3 = f"{uuid.uuid4()} name"
        project_id = f"project_{uuid.uuid4()}"
        description = f"description_{uuid.uuid4()}"
        workflow = "SDSX"

        submission_id_1 = await self.post_submission(
            name=name_1, description=description, project_id=project_id, workflow=workflow
        )
        submission_id_2 = await self.post_submission(
            name=name_2, description=description, project_id=project_id, workflow=workflow
        )
        submission_id_3 = await self.post_submission(
            name=name_3, description=description, project_id=project_id, workflow=workflow
        )

        with (
            self.patch_verify_user_project,
            self.patch_verify_authorization,
        ):
            response = await self.client.get(f"{API_PREFIX}/submissions?projectId={project_id}&name=name")
            self.assertEqual(response.status, 200)
            result = await response.json()
            assert len(result["submissions"]) == 2
            assert submission_id_1 in [r["submissionId"] for r in result["submissions"]]
            assert submission_id_3 in [r["submissionId"] for r in result["submissions"]]

    async def test_get_submissions_by_created(self):
        """Test that get submissions by created date."""

        project_id = f"project_{uuid.uuid4()}"
        submission_id = await self.post_submission(project_id=project_id)

        def today_with_offset(days: int = 0) -> str:
            """Return the current date plus or minus the given number of days in the format 'YYYY-MM-DD'."""

            target_date = datetime.today() + timedelta(days=days)
            return target_date.strftime("%Y-%m-%d")

        with (
            self.patch_verify_user_project,
            self.patch_verify_authorization,
        ):

            async def get_submissions(created_start, created_end):
                if created_start and created_end:
                    response = await self.client.get(
                        f"{API_PREFIX}/submissions?projectId={project_id}&date_created_start={created_start}&date_created_end={created_end}"
                    )
                elif created_start:
                    response = await self.client.get(
                        f"{API_PREFIX}/submissions?projectId={project_id}&date_created_start={created_start}"
                    )
                elif created_end:
                    response = await self.client.get(
                        f"{API_PREFIX}/submissions?projectId={project_id}&date_created_end={created_end}"
                    )
                else:
                    assert False

                assert response.status == 200
                return await response.json()

            async def assert_included(created_start, created_end):
                result = await get_submissions(created_start, created_end)
                assert len(result["submissions"]) == 1
                assert submission_id in [r["submissionId"] for r in result["submissions"]]

            async def assert_not_included(created_start, created_end):
                result = await get_submissions(created_start, created_end)
                assert len(result["submissions"]) == 0

            await assert_included(today_with_offset(-1), today_with_offset(1))
            await assert_included(today_with_offset(0), today_with_offset(1))
            await assert_included(today_with_offset(-1), today_with_offset(0))
            await assert_included(today_with_offset(0), today_with_offset(0))
            await assert_included(today_with_offset(-1), None)
            await assert_included(today_with_offset(0), None)
            await assert_included(None, today_with_offset(1))
            await assert_included(None, today_with_offset(0))

            await assert_not_included(today_with_offset(-1), today_with_offset(-1))
            await assert_not_included(today_with_offset(1), today_with_offset(1))
            await assert_not_included(today_with_offset(1), None)
            await assert_not_included(None, today_with_offset(-1))

    async def test_get_submissions_by_modified(self):
        """Test that get submissions by modified date."""

        project_id = f"project_{uuid.uuid4()}"
        submission_id = await self.post_submission(project_id=project_id)

        def today_with_offset(days: int = 0) -> str:
            """Return the current date plus or minus the given number of days in the format 'YYYY-MM-DD'."""

            target_date = datetime.today() + timedelta(days=days)
            return target_date.strftime("%Y-%m-%d")

        with (
            self.patch_verify_user_project,
            self.patch_verify_authorization,
        ):

            async def get_submissions(modified_start, modified_end):
                if modified_start and modified_end:
                    response = await self.client.get(
                        f"{API_PREFIX}/submissions?projectId={project_id}&date_modified_start={modified_start}&date_modified_end={modified_end}"
                    )
                elif modified_start:
                    response = await self.client.get(
                        f"{API_PREFIX}/submissions?projectId={project_id}&date_modified_start={modified_start}"
                    )
                elif modified_end:
                    response = await self.client.get(
                        f"{API_PREFIX}/submissions?projectId={project_id}&date_modified_end={modified_end}"
                    )
                else:
                    assert False

                assert response.status == 200
                return await response.json()

            async def assert_included(modified_start, modified_end):
                result = await get_submissions(modified_start, modified_end)
                assert len(result["submissions"]) == 1
                assert submission_id in [r["submissionId"] for r in result["submissions"]]

            async def assert_not_included(modified_start, modified_end):
                result = await get_submissions(modified_start, modified_end)
                assert len(result["submissions"]) == 0

            await assert_included(today_with_offset(-1), today_with_offset(1))
            await assert_included(today_with_offset(0), today_with_offset(1))
            await assert_included(today_with_offset(-1), today_with_offset(0))
            await assert_included(today_with_offset(0), today_with_offset(0))
            await assert_included(today_with_offset(-1), None)
            await assert_included(today_with_offset(0), None)
            await assert_included(None, today_with_offset(1))
            await assert_included(None, today_with_offset(0))

            await assert_not_included(today_with_offset(-1), today_with_offset(-1))
            await assert_not_included(today_with_offset(1), today_with_offset(1))
            await assert_not_included(today_with_offset(1), None)
            await assert_not_included(None, today_with_offset(-1))

    async def test_get_submissions_with_no_submissions(self):
        """Test that get submissions works without project id."""
        with (
            self.patch_verify_user_project,
            self.patch_verify_authorization,
        ):
            project_id = f"project_{uuid.uuid4()}"

            response = await self.client.get(f"{API_PREFIX}/submissions?projectId={project_id}")
            self.assertEqual(response.status, 200)
            result = {
                "page": {
                    "page": 1,
                    "size": 5,
                    "totalPages": 0,
                    "totalSubmissions": 0,
                },
                "submissions": [],
            }
            self.assertEqual(await response.json(), result)

    async def test_get_submissions_fails_with_invalid_parameters(self):
        """Test that get submissions fails with invalid parameters."""
        with (
            self.patch_verify_user_project,
            self.patch_verify_authorization,
        ):
            response = await self.client.get(f"{API_PREFIX}/submissions?page=ayylmao&projectId=1000")
            self.assertEqual(response.status, 400)
            resp = await response.json()
            self.assertEqual(resp["detail"], "page parameter must be a number, now it is ayylmao")

            response = await self.client.get(f"{API_PREFIX}/submissions?page=1&per_page=-100&projectId=1000")
            self.assertEqual(response.status, 400)
            resp = await response.json()
            self.assertEqual(resp["detail"], "per_page parameter must be over 0")

            response = await self.client.get(f"{API_PREFIX}/submissions?published=yes&projectId=1000")
            self.assertEqual(response.status, 400)
            resp = await response.json()
            self.assertEqual(resp["detail"], "'published' parameter must be either 'true' or 'false'")

    async def test_patch_submission(self):
        """Test that submission patch works with correct keys."""
        name = f"name_{uuid.uuid4()}"
        project_id = f"project_{uuid.uuid4()}"
        description = f"description_{uuid.uuid4()}"
        workflow = "SDSX"

        submission_id = await self.post_submission(
            name=name, description=description, project_id=project_id, workflow=workflow
        )

        # Update name.

        new_name = f"name_{uuid.uuid4()}"
        data = {"name": new_name}
        with (
            self.patch_verify_user_project,
            self.patch_verify_authorization,
        ):
            response = await self.client.patch(f"{API_PREFIX}/submissions/{submission_id}", json=data)
            self.assertEqual(response.status, 200)

        submission = await self.get_submission(submission_id)
        assert submission["name"] == new_name
        assert submission["description"] == description
        assert submission["projectId"] == project_id
        assert submission["workflow"] == workflow

        # Update description.

        new_description = f"description_{uuid.uuid4()}"
        data = {"description": new_description}
        with (
            self.patch_verify_user_project,
            self.patch_verify_authorization,
        ):
            response = await self.client.patch(f"{API_PREFIX}/submissions/{submission_id}", json=data)
            self.assertEqual(response.status, 200)

        submission = await self.get_submission(submission_id)
        assert submission["name"] == new_name
        assert submission["description"] == new_description
        assert submission["projectId"] == project_id
        assert submission["workflow"] == workflow

    async def test_patch_doi_info(self):
        """Test changing doi info in the submission."""
        submission_id = await self.post_submission()

        data = ujson.load(open(self.TESTFILES_ROOT / "doi" / "test_doi.json"))

        with (
            self.patch_verify_user_project,
            self.patch_verify_authorization,
        ):
            response = await self.client.patch(f"{API_PREFIX}/submissions/{submission_id}/doi", json=data)
            self.assertEqual(response.status, 200)

        submission = await self.get_submission(submission_id)
        assert data == submission["doiInfo"]

    async def test_patch_linked_folder(self):
        """Test changing linked folder in the submission."""
        submission_id = await self.post_submission()
        folder = f"folder_{uuid.uuid4()}"
        data = {"linkedFolder": folder}

        # Set linked folder for the first time works.
        with (
            self.patch_verify_user_project,
            self.patch_verify_authorization,
        ):
            response = await self.client.patch(f"{API_PREFIX}/submissions/{submission_id}/folder", json=data)
            self.assertEqual(response.status, 204)

        submission = await self.get_submission(submission_id)
        assert submission["linkedFolder"] == folder

        # Change linked folder fails.
        with (
            self.patch_verify_user_project,
            self.patch_verify_authorization,
        ):
            response = await self.client.patch(f"{API_PREFIX}/submissions/{submission_id}/folder", json=data)
            self.assertEqual(response.status, 400)
            self.assertIn("already has a linked folder", await response.text())

        submission = await self.get_submission(submission_id)
        assert submission["linkedFolder"] == folder

    async def test_patch_rems(self):
        """Test changing rems in the submission."""
        submission_id = await self.post_submission()

        # Set rems with the correct fields works.

        data = {"workflowId": 1, "organizationId": "CSC", "licenses": [1]}

        with self.patch_verify_user_project, self.patch_verify_authorization, self.patch_verify_rems_workflow_licence:
            response = await self.client.patch(f"{API_PREFIX}/submissions/{submission_id}/rems", json=data)
            self.assertEqual(response.status, 200)

        submission = await self.get_submission(submission_id)
        assert submission["rems"] == data

        # Change rems with the correct fields works.

        data = {"workflowId": 2, "organizationId": "CSC", "licenses": [2]}

        with self.patch_verify_user_project, self.patch_verify_authorization, self.patch_verify_rems_workflow_licence:
            response = await self.client.patch(f"{API_PREFIX}/submissions/{submission_id}/rems", json=data)
            self.assertEqual(response.status, 200)

        submission = await self.get_submission(submission_id)
        assert submission["rems"] == data

        # Change rems with missing fields fails.

        data = {
            "workflowId": 3,
        }

        with self.patch_verify_user_project, self.patch_verify_authorization, self.patch_verify_rems_workflow_licence:
            response = await self.client.patch(f"{API_PREFIX}/submissions/{submission_id}/rems", json=data)
            self.assertEqual(response.status, 400)
            self.assertIn("Field required", await response.text())

        # Change rems with invalid types fails.

        data = {"workflowId": "invalid", "organizationId": "CSC", "licenses": [3]}

        with self.patch_verify_user_project, self.patch_verify_authorization, self.patch_verify_rems_workflow_licence:
            response = await self.client.patch(f"{API_PREFIX}/submissions/{submission_id}/rems", json=data)
            self.assertEqual(response.status, 400)
            self.assertIn("Input should be a valid integer", await response.text())
