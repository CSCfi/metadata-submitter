"""Test operations with submissions."""

import logging
import uuid

from tests.integration.conf import submit_url
from tests.integration.helpers import (
    get_submission,
    submissions_url,
)
from tests.utils import sd_submission_document

LOG = logging.getLogger(__name__)
LOG.setLevel(logging.DEBUG)


async def test_sd_submission(sd_client, sd_submission, sd_submission_update, project_id):
    """Test post, get and delete SD submission using /submit endpoint."""

    # Create submission.
    submission = await sd_submission(submit_endpoint=True)
    submission_id = submission.submissionId

    # Create another submission with the same name fails.
    data = sd_submission_document(submission)
    async with sd_client.post(f"{submit_url}?projectId={project_id}", data=data) as resp:
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
    async with sd_client.delete(f"{submit_url}/{submission_id}?projectId={project_id}") as resp:
        assert resp.status == 204

    # Get submission using /submissions endpoint.
    async with sd_client.get(f"{submissions_url}/{submission_id}") as resp:
        assert resp.status == 404


async def test_bp_submission(nbis_client, bp_submission, bp_submission_update, project_id):
    """Test post, get and delete BP submission using /submit endpoint."""

    for is_datacite in [True, False]:
        # Create submission.
        submission, object_names = await bp_submission(is_datacite)
        submission_id = submission.submissionId

        # Get submission using /submissions endpoint.
        saved_submission = await get_submission(nbis_client, submission_id)
        assert saved_submission.submissionId == submission_id
        assert saved_submission.name == submission.name
        assert saved_submission.description == submission.description
        assert not saved_submission.published

        # Update submission (no XML changes).
        await bp_submission_update(submission.submissionId, submission.name, object_names, is_datacite)

        # Delete submission.
        async with nbis_client.delete(f"{submit_url}/{submission_id}") as resp:
            assert resp.status == 204

        # Get submission using /submissions endpoint.
        async with nbis_client.get(f"{submissions_url}/{submission_id}") as resp:
            assert resp.status == 404
