"""Test API endpoints from handlers module."""

import uuid
from datetime import date
from typing import Any

from fastapi.testclient import TestClient

from metadata_backend.conf.conf import API_PREFIX
from tests.unit.patches.user import patch_verify_authorization, patch_verify_user_project

SUBMISSION_METADATA = {
    "publicationYear": date.today().year,
    "creators": [
        {
            "givenName": "Test",
            "familyName": "Creator",
            "affiliation": [
                {
                    "name": "affiliation place",
                    "schemeUri": "https://ror.org",
                    "affiliationIdentifier": "https://ror.org/test1",
                    "affiliationIdentifierScheme": "ROR",
                }
            ],
        }
    ],
    "subjects": [{"subject": "999 - Other"}],
    "keywords": "test,keyword",
    "publisher": {"name": "University Health Care System"},
}


async def sd_submission(
    client: TestClient,
    name: str | None = None,
    title: str | None = None,
    description: str | None = None,
    project_id: str | None = None,
    *,
    submission: dict[str, Any] | None = None,
) -> str | tuple[str, dict[str, Any]]:
    """Post a SD submission."""

    is_submission = submission is not None

    if name is None:
        name = f"name_{uuid.uuid4()}"
    if title is None:
        title = f"title_{uuid.uuid4()}"
    if description is None:
        description = f"description_{uuid.uuid4()}"
    if project_id is None:
        project_id = f"project_{uuid.uuid4()}"

    with (
        patch_verify_authorization,
        patch_verify_user_project,
    ):
        if not is_submission:
            submission = {
                "name": name,
                "title": title,
                "description": description,
                "projectId": project_id,
            }
        else:
            submission["name"] = name
            submission["title"] = title
            submission["description"] = description
            submission["projectId"] = project_id

        response = client.post(f"{API_PREFIX}/submissions", json=submission)
        response.raise_for_status()

        submission_id = response.json()["submissionId"]

        if is_submission:
            return submission_id, submission
        return submission_id


async def get_submission(client: TestClient, submission_id) -> dict[str, Any]:
    """Get a submission."""
    with (
        patch_verify_user_project,
        patch_verify_authorization,
    ):
        response = client.get(f"{API_PREFIX}/submissions/{submission_id}")
        response.raise_for_status()
        return response.json()
