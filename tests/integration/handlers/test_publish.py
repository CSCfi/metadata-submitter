"""Test publish handler."""

import json
import logging

from aiohttp import ClientSession

from tests.integration.conf import (
    SD_SUBMISSION,
    publish_url,
    submissions_url,
)
from tests.integration.helpers import (
    get_registrations,
    get_submission,
    publish_submission,
)

LOG = logging.getLogger(__name__)
LOG.setLevel(logging.DEBUG)


async def test_publish_csc(sd_client, sd_submission):
    """Test publish for CSC deployment without testing files."""

    submission_dict = json.loads(SD_SUBMISSION.read_text())

    # Create submission.
    submission = await sd_submission(submission_dict)
    assert submission.submissionId is not None
    assert submission.published is False
    assert submission.datePublished is None
    submission_id = submission.submissionId

    # Publish submission.
    await publish_submission(sd_client, submission_id, no_files=True)

    # Get published submission.
    published_submission = await get_submission(sd_client, submission_id)
    assert published_submission.submissionId == submission_id
    assert published_submission.published is True
    assert published_submission.datePublished is not None

    # Get registrations.
    registration = await get_registrations(sd_client, submission_id)
    assert registration.submissionId == submission_id
    assert registration.title == "TestTitle"
    assert registration.description == "TestDescription"
    assert registration.doi.startswith("10.80869")
    assert registration.metaxId is not None
    assert registration.remsResourceId is not None
    assert registration.remsCatalogueId is not None
    assert registration.remsUrl is not None

    await assert_immutable_after_publish(sd_client, submission.submissionId)


async def test_publish_nbis(nbis_client, bp_submission):
    """Test publish for NBIS deployment."""

    # Create submission.
    submission = await bp_submission()
    assert submission.submissionId is not None
    assert submission.published is False
    assert submission.datePublished is None
    submission_id = submission.submissionId

    # Publish submission.
    await publish_submission(nbis_client, submission_id)

    # Get published submission.
    published_submission = await get_submission(nbis_client, submission_id)
    assert published_submission.submissionId == submission_id
    assert published_submission.published is True
    assert published_submission.datePublished is not None

    # Get registrations.
    registration = await get_registrations(nbis_client, submission_id)
    assert registration.doi.startswith("10.80869")
    assert registration.metaxId is None
    assert registration.remsResourceId is not None
    assert registration.remsCatalogueId is not None
    assert registration.remsUrl is not None

    await assert_immutable_after_publish(nbis_client, submission_id)


async def assert_immutable_after_publish(client: ClientSession, submission_id: str):
    """Assert that the submission can't be changes after publishing."""

    # Check that submission can't be changed.
    async with client.patch(f"{submissions_url}/{submission_id}", data=json.dumps({"name": "new_name"})) as resp:
        assert resp.status == 400

    # Check that submission can't be re-published.
    async with client.patch(f"{publish_url}/{submission_id}") as resp:
        assert resp.status == 400

    # Check that submission can't be deleted.
    async with client.delete(f"{submissions_url}/{submission_id}") as resp:
        assert resp.status == 400
