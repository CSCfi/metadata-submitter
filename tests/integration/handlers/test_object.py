"""Test operations with submissions."""

import logging
import uuid

from tests.integration.conf import submit_url
from tests.integration.conftest import bp_submit_multipart_data, sd_submit_multipart_data
from tests.integration.helpers import (
    get_submission,
    submissions_url,
)

LOG = logging.getLogger(__name__)
LOG.setLevel(logging.DEBUG)


async def test_sd_submission(sd_client, sd_submission, sd_submission_update, project_id):
    """Test post, get and delete SD submission using /submit endpoint."""

    # Create submission.
    submission = await sd_submission(submit_endpoint=True)
    submission_id = submission.submissionId

    # Create another submission with the same name fails.
    data = sd_submit_multipart_data(submission)
    async with sd_client.post(f"{submit_url}/{submission.workflow.value}?projectId={project_id}", data=data) as resp:
        res = await resp.json()
        assert resp.status == 400
        assert (
            res["errors"][0]
            == f"Submission with name '{submission.name}' already exists in project '{submission.projectId}'"
        )

    # Get submission using /submissions endpoint.
    saved_submission = await get_submission(sd_client, submission_id)
    assert saved_submission.submissionId == submission_id
    assert saved_submission.name == submission.name
    assert saved_submission.description == submission.description
    assert not saved_submission.published

    # Update submission.
    updated_title = f"name_{uuid.uuid4()}"
    updated_submission = await sd_submission_update(
        submission.submissionId, {"title": updated_title}, submit_endpoint=True
    )
    assert updated_submission.title == updated_title

    # Delete submission.
    async with sd_client.delete(
        f"{submit_url}/{submission.workflow.value}/{submission_id}?projectId={project_id}"
    ) as resp:
        assert resp.status == 204

    # Get submission using /submissions endpoint.
    async with sd_client.get(f"{submissions_url}/{submission_id}") as resp:
        assert resp.status == 404


async def test_nbis_submission(nbis_client, bp_submission, bp_submission_update, project_id):
    """Test post, get and delete NBIS BigPicture submission using /submit endpoint."""

    # Create submission.
    submission = await bp_submission()
    submission_id = submission.submissionId

    # Create another submission with the same name fails.
    submission_name, data = bp_submit_multipart_data()
    async with nbis_client.post(f"{submit_url}/{submission.workflow.value}", data=data) as resp:
        res = await resp.json()
        assert resp.status == 400
        assert (
            f"Submission with name '{submission.name}' already exists in project '{submission.projectId}'"
            in res["errors"]
        )

    # Get submission using /submissions endpoint.
    saved_submission = await get_submission(nbis_client, submission_id)
    assert saved_submission.submissionId == submission_id
    assert saved_submission.name == submission.name
    assert saved_submission.description == submission.description
    assert not saved_submission.published

    # Update submission (submission title and description are extracted from dataset).
    assert submission.title == "test_title"
    assert submission.description == "test_description"
    updated_submission = await bp_submission_update(submission.submissionId)
    assert updated_submission.title == "updated_test_title"
    assert updated_submission.description == "updated_test_description"

    # Delete submission.
    async with nbis_client.delete(f"{submit_url}/{submission.workflow.value}/{submission_id}") as resp:
        assert resp.status == 204

    # Get submission using /submissions endpoint.
    async with nbis_client.get(f"{submissions_url}/{submission_id}") as resp:
        assert resp.status == 404
