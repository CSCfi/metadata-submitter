"""Tests for submission API handler."""

import json
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from metadata_backend.api.handlers.submission import SubmissionAPIHandler
from metadata_backend.conf.conf import API_PREFIX
from tests.unit.patches.user import patch_verify_authorization, patch_verify_user_project

from .common import get_submission, post_submission

TEST_ROOT_DIR = Path(__file__).parent.parent.parent.parent / "test_files"
SUBMISSION_JSON = TEST_ROOT_DIR / "submission" / "submission.json"


async def test_post_get_delete_submission(csc_client):
    """Test that submission post and get works."""

    # Test valid submission.

    name = f"name_{uuid.uuid4()}"
    description = f"description_{uuid.uuid4()}"
    project_id = f"project_{uuid.uuid4()}"
    workflow = "SD"

    # Post submission.

    submission_id = await post_submission(
        csc_client, name=name, description=description, project_id=project_id, workflow=workflow
    )

    # Get submission.

    submission = await get_submission(csc_client, submission_id)

    assert submission["name"] == name
    assert submission["description"] == description
    assert submission["projectId"] == project_id
    assert submission["workflow"] == workflow

    # Delete submission.

    with (
        patch_verify_user_project,
        patch_verify_authorization,
    ):
        response = csc_client.delete(f"{API_PREFIX}/submissions/{submission_id}")
        assert response.status_code == 204

    # Get submission.

    with (
        patch_verify_user_project,
        patch_verify_authorization,
    ):
        response = csc_client.get(f"{API_PREFIX}/submissions/{submission_id}")
        assert response.status_code == 404


async def test_post_submission_fails_with_missing_fields(csc_client):
    """Test that submission creation fails with missing fields."""

    data = {
        "name": f"name_{uuid.uuid4()}",
        "title": f"title_{uuid.uuid4()}",
        "description": f"description_{uuid.uuid4()}",
        "projectId": f"project_{uuid.uuid4()}",
        "workflow": "SD",
    }

    async def assert_missing_field(field: str):
        _data = {k: v for k, v in data.items() if k != field}
        with patch_verify_authorization:
            response = csc_client.post(f"{API_PREFIX}/submissions", json=_data)
            assert response.status_code == 400

    await assert_missing_field("name")
    await assert_missing_field("description")
    await assert_missing_field("projectId")
    await assert_missing_field("workflow")


async def test_post_submission_fails_with_empty_body(csc_client):
    """Test that submission creation fails when no data in request."""
    with patch_verify_authorization:
        response = csc_client.post(f"{API_PREFIX}/submissions")
        result = response.json()
        assert result == {
            "detail": "Validation error",
            "errors": [{"field": "body", "message": "Field required"}],
            "instance": "/v1/submissions",
            "status": 400,
            "title": "Bad Request",
            "type": "about:blank",
        }


async def test_post_submission_fails_with_duplicate_name(csc_client):
    """Test that submission creation fails if the submission name already exists in the project."""
    name = f"name_{uuid.uuid4()}"
    project_id = f"project_{uuid.uuid4()}"

    await post_submission(csc_client, name=name, project_id=project_id)

    data = {
        "name": name,
        "title": f"title_{uuid.uuid4()}",
        "description": f"description_{uuid.uuid4()}",
        "projectId": project_id,
        "workflow": "SD",
    }

    with (
        patch_verify_user_project,
        patch_verify_authorization,
    ):
        response = csc_client.post(f"{API_PREFIX}/submissions", json=data)
        json_resp = response.json()
        assert response.status_code == 400
        assert f"Submission with name '{name}' already exists in project {project_id}" == json_resp["detail"]


async def test_get_submissions(csc_client):
    """Test that get submissions works."""

    name_1 = f"name_{uuid.uuid4()}"
    name_2 = f"name_{uuid.uuid4()}"
    project_id = f"project_{uuid.uuid4()}"
    title = f"title_{uuid.uuid4()}"
    description = f"description_{uuid.uuid4()}"
    workflow = "SD"

    submission_id_1 = await post_submission(
        csc_client, name=name_1, title=title, description=description, project_id=project_id, workflow=workflow
    )
    submission_id_2 = await post_submission(
        csc_client, name=name_2, title=title, description=description, project_id=project_id, workflow=workflow
    )

    with (
        patch_verify_user_project,
        patch_verify_authorization,
    ):
        response = csc_client.get(f"{API_PREFIX}/submissions?projectId={project_id}")
        assert response.status_code == 200
        result = response.json()

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
            "workflow": workflow,
        } in result["submissions"]


async def test_get_submissions_by_name(csc_client):
    """Test that get submissions by name works."""

    name_1 = f"name_{uuid.uuid4()}"
    name_2 = f"{uuid.uuid4()}"
    name_3 = f"{uuid.uuid4()} name"
    project_id = f"project_{uuid.uuid4()}"
    description = f"description_{uuid.uuid4()}"
    workflow = "SD"

    submission_id_1 = await post_submission(
        csc_client, name=name_1, description=description, project_id=project_id, workflow=workflow
    )
    await post_submission(csc_client, name=name_2, description=description, project_id=project_id, workflow=workflow)
    submission_id_3 = await post_submission(
        csc_client, name=name_3, description=description, project_id=project_id, workflow=workflow
    )

    with (
        patch_verify_user_project,
        patch_verify_authorization,
    ):
        response = csc_client.get(f"{API_PREFIX}/submissions?projectId={project_id}&name=name")
        assert response.status_code == 200
        result = response.json()
        assert len(result["submissions"]) == 2
        assert submission_id_1 in [r["submissionId"] for r in result["submissions"]]
        assert submission_id_3 in [r["submissionId"] for r in result["submissions"]]


async def test_get_submissions_by_created(csc_client):
    """Test that get submissions by created date."""

    project_id = f"project_{uuid.uuid4()}"
    submission_id = await post_submission(csc_client, project_id=project_id)

    def today_with_offset(days: int = 0) -> str:
        """Return the current date plus or minus the given number of days in the format 'YYYY-MM-DD'."""

        target_date = datetime.today() + timedelta(days=days)
        return target_date.strftime("%Y-%m-%d")

    with (
        patch_verify_user_project,
        patch_verify_authorization,
    ):

        async def get_submissions(created_start, created_end):
            if created_start and created_end:
                response = csc_client.get(
                    f"{API_PREFIX}/submissions?projectId={project_id}&date_created_start={created_start}&date_created_end={created_end}"
                )
            elif created_start:
                response = csc_client.get(
                    f"{API_PREFIX}/submissions?projectId={project_id}&date_created_start={created_start}"
                )
            elif created_end:
                response = csc_client.get(
                    f"{API_PREFIX}/submissions?projectId={project_id}&date_created_end={created_end}"
                )
            else:
                assert False

            assert response.status_code == 200
            return response.json()

        async def assert_included(created_start, created_end):
            result = await get_submissions(created_start, created_end)
            assert len(result["submissions"]) == 1
            assert submission_id in [r["submissionId"] for r in result["submissions"]]

        async def assert_not_included(created_start, created_end):
            result = await get_submissions(created_start, created_end)
            assert len(result["submissions"]) == 0

        await assert_included(today_with_offset(-1), today_with_offset(1))
        await assert_included(today_with_offset(-1), today_with_offset(0))
        await assert_included(today_with_offset(-1), None)
        await assert_included(None, today_with_offset(1))
        await assert_included(None, today_with_offset(0))
        await assert_not_included(today_with_offset(1), today_with_offset(1))
        await assert_not_included(today_with_offset(1), None)


async def test_get_submissions_by_modified(csc_client):
    """Test that get submissions by modified date."""

    project_id = f"project_{uuid.uuid4()}"
    submission_id = await post_submission(csc_client, project_id=project_id)

    def today_with_offset(days: int = 0) -> str:
        """Return the current date plus or minus the given number of days in the format 'YYYY-MM-DD'."""

        target_date = datetime.today() + timedelta(days=days)
        return target_date.strftime("%Y-%m-%d")

    with (
        patch_verify_user_project,
        patch_verify_authorization,
    ):

        async def get_submissions(modified_start, modified_end):
            if modified_start and modified_end:
                response = csc_client.get(
                    f"{API_PREFIX}/submissions?projectId={project_id}&date_modified_start={modified_start}&date_modified_end={modified_end}"
                )
            elif modified_start:
                response = csc_client.get(
                    f"{API_PREFIX}/submissions?projectId={project_id}&date_modified_start={modified_start}"
                )
            elif modified_end:
                response = csc_client.get(
                    f"{API_PREFIX}/submissions?projectId={project_id}&date_modified_end={modified_end}"
                )
            else:
                assert False

            assert response.status_code == 200
            return response.json()

        async def assert_included(modified_start, modified_end):
            result = await get_submissions(modified_start, modified_end)
            assert len(result["submissions"]) == 1
            assert submission_id in [r["submissionId"] for r in result["submissions"]]

        async def assert_not_included(modified_start, modified_end):
            result = await get_submissions(modified_start, modified_end)
            assert len(result["submissions"]) == 0

        await assert_included(today_with_offset(-1), today_with_offset(1))
        await assert_included(today_with_offset(-1), today_with_offset(0))
        await assert_included(today_with_offset(-1), None)
        await assert_included(None, today_with_offset(1))

        await assert_not_included(today_with_offset(1), today_with_offset(1))
        await assert_not_included(today_with_offset(1), None)


async def test_get_submissions_with_no_submissions(csc_client):
    """Test that get submissions works without project id."""
    with (
        patch_verify_user_project,
        patch_verify_authorization,
    ):
        project_id = f"project_{uuid.uuid4()}"

        response = csc_client.get(f"{API_PREFIX}/submissions?projectId={project_id}")
        assert response.status_code == 200
        result = {
            "page": {
                "page": 1,
                "size": 5,
                "totalPages": 0,
                "totalSubmissions": 0,
            },
            "submissions": [],
        }
        assert response.json() == result


async def test_get_submissions_invalid_parameters(csc_client):
    """Test that get submissions fails with invalid parameters."""
    with (
        patch_verify_user_project,
        patch_verify_authorization,
    ):
        response = csc_client.get(f"{API_PREFIX}/submissions?page=invalid&projectId=1000")
        assert response.status_code == 400
        resp = response.json()
        assert resp == {
            "detail": "Validation error",
            "errors": [
                {
                    "field": "query.page",
                    "message": "Input should be a valid integer, unable to parse string as an integer",
                }
            ],
            "instance": "/v1/submissions",
            "status": 400,
            "title": "Bad Request",
            "type": "about:blank",
        }

        response = csc_client.get(f"{API_PREFIX}/submissions?page=1&per_page=-100&projectId=1000")
        assert response.status_code == 400
        resp = response.json()
        assert resp == {
            "detail": "Validation error",
            "errors": [{"field": "query.per_page", "message": "Input should be greater than or equal to 1"}],
            "instance": "/v1/submissions",
            "status": 400,
            "title": "Bad Request",
            "type": "about:blank",
        }

        response = csc_client.get(f"{API_PREFIX}/submissions?published=maybe&projectId=1000")
        assert response.status_code == 400
        resp = response.json()
        assert resp == {
            "detail": "Validation error",
            "errors": [
                {"field": "query.published", "message": "Input should be a valid boolean, unable to interpret input"}
            ],
            "instance": "/v1/submissions",
            "status": 400,
            "title": "Bad Request",
            "type": "about:blank",
        }


async def test_patch_submission(csc_client):
    """Test that submission patch works with correct keys."""
    name = f"name_{uuid.uuid4()}"
    project_id = f"project_{uuid.uuid4()}"
    description = f"description_{uuid.uuid4()}"
    workflow = "SD"

    submission_id = await post_submission(
        csc_client, name=name, description=description, project_id=project_id, workflow=workflow
    )

    # Update title.

    new_title = f"title_{uuid.uuid4()}"
    data = {"title": new_title}
    with (
        patch_verify_user_project,
        patch_verify_authorization,
    ):
        response = csc_client.patch(f"{API_PREFIX}/submissions/{submission_id}", json=data)
        assert response.status_code == 200

    submission = await get_submission(csc_client, submission_id)
    assert submission["title"] == new_title
    assert submission["description"] == description
    assert submission["projectId"] == project_id
    assert submission["workflow"] == workflow

    # Update description.

    new_description = f"description_{uuid.uuid4()}"
    data = {"description": new_description}
    with (
        patch_verify_user_project,
        patch_verify_authorization,
    ):
        response = csc_client.patch(f"{API_PREFIX}/submissions/{submission_id}", json=data)
        assert response.status_code == 200

    submission = await get_submission(csc_client, submission_id)
    assert submission["title"] == new_title
    assert submission["description"] == new_description
    assert submission["projectId"] == project_id
    assert submission["workflow"] == workflow


async def test_submission_json(csc_client):
    """Test that submission json test file works."""

    submission = json.loads(SUBMISSION_JSON.read_text())

    # Test valid submission.

    name = f"name_{uuid.uuid4()}"

    description = f"description_{uuid.uuid4()}"
    project_id = f"project_{uuid.uuid4()}"
    workflow = "SD"

    # Post submission.

    submission_id, submission = await post_submission(
        csc_client, name=name, description=description, project_id=project_id, workflow=workflow, submission=submission
    )

    # Get submission.

    saved_submission = await get_submission(csc_client, submission_id)

    assert saved_submission["dateCreated"] is not None
    assert saved_submission["lastModified"] is not None
    assert saved_submission["published"] is False
    assert saved_submission["submissionId"] == submission_id

    del saved_submission["dateCreated"]
    del saved_submission["lastModified"]
    del saved_submission["published"]
    del saved_submission["submissionId"]

    assert submission == saved_submission


@pytest.mark.parametrize(
    "page,page_size,total_submissions,expected",
    [
        # first page, 4 pages total
        (
            1,
            10,
            35,
            '<https://test.com?page=1&per_page=10>; rel="first", '
            '<https://test.com?page=2&per_page=10>; rel="next", '
            '<https://test.com?page=4&per_page=10>; rel="last"',
        ),
        # second page
        (
            2,
            10,
            35,
            '<https://test.com?page=1&per_page=10>; rel="first", '
            '<https://test.com?page=1&per_page=10>; rel="prev", '
            '<https://test.com?page=3&per_page=10>; rel="next", '
            '<https://test.com?page=4&per_page=10>; rel="last"',
        ),
        # last page
        (
            4,
            10,
            35,
            '<https://test.com?page=1&per_page=10>; rel="first", '
            '<https://test.com?page=3&per_page=10>; rel="prev", '
            '<https://test.com?page=4&per_page=10>; rel="last"',
        ),
        # single page
        (
            1,
            10,
            5,
            '<https://test.com?page=1&per_page=10>; rel="first", <https://test.com?page=1&per_page=10>; rel="last"',
        ),
        # no submissions
        (1, 10, 0, None),
    ],
)
def test_link_header(page, page_size, total_submissions, expected):
    """Test Link header."""
    url = "https://test.com"
    headers = SubmissionAPIHandler._link_header(url, page, page_size, total_submissions)

    if expected is None:
        assert headers is None
    else:
        assert "Link" in headers
        assert headers["Link"] == expected
