"""Test publish handler."""

import json
import logging
from unittest.mock import AsyncMock

import pytest
from aiohttp import ClientSession

from metadata_backend.api.services.file import S3InboxSDAService
from metadata_backend.conf.deployment import deployment_config
from tests.integration.conf import (
    mock_inbox_url,
    mock_s3_region,
    mock_user,
)
from tests.integration.helpers import (
    add_bucket,
    get_files,
    get_registrations,
    get_submission,
    get_user_id,
    publish_submission,
    seed_mock_admin_files,
)
from tests.utils import BigpictureObjectNames, bp_update_documents, sd_submission_dict

LOG = logging.getLogger(__name__)
LOG.setLevel(logging.DEBUG)


async def test_publish_sd(sd_client, sd_submission):
    """Test publish SD for CSC deployment."""

    submission_dict = sd_submission_dict()

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

    await assert_immutable_after_publish_sd(sd_client, submission.submissionId)


async def test_publish_bp(nbis_client, bp_submission):
    """Test publish BP for NBIS deployment."""

    # Create bucket for the test user in the mock S3 inbox.
    bucket = mock_user.replace("@", "_")
    await add_bucket(bucket, bucket, bucket, mock_inbox_url, mock_s3_region)

    for is_datacite in [True, False]:
        # Create submission.
        submission, object_names = await bp_submission(is_datacite)
        assert submission.submissionId is not None
        assert submission.published is False
        assert submission.datePublished is None
        submission_id = submission.submissionId

        # Mock Admin keeps inbox file state separate from S3; seed file paths for ingest polling.
        await seed_mock_admin_files(nbis_client, mock_user, submission_id)

        # Publish submission.
        await publish_submission(nbis_client, submission_id, no_files=False)

        # Get published submission.
        published_submission = await get_submission(nbis_client, submission_id)
        assert published_submission.submissionId == submission_id
        assert published_submission.published is True
        assert published_submission.datePublished is not None

        # Get registrations.
        registration = await get_registrations(nbis_client, submission_id)
        if is_datacite:
            assert registration.doi.startswith("10.80869")
        assert registration.metaxId is None
        assert registration.remsResourceId is not None
        assert registration.remsCatalogueId is not None
        assert registration.remsUrl is not None

        await assert_immutable_after_publish_bp(nbis_client, submission_id, submission.name, object_names, is_datacite)


@pytest.mark.skip(reason="This test is for manual testing against staging environment and requires manual setup.")
async def test_real_publish_bp(nbis_client, bp_submission, monkeypatch):
    # To run this test against the staging SDA pipeline
    # Set NBIS_JWT environment variable to a valid upload JWT token

    # Create new submission
    submission, _ = await bp_submission(is_datacite=True)
    assert submission.submissionId is not None
    submission_id = submission.submissionId

    # Check submission files to be uploaded to S3 inbox
    get_files_response = await get_files(nbis_client, submission_id)
    assert len(get_files_response) == 3
    filenames = {file["path"] for file in get_files_response}
    # assert filenames == {
    #     f"DATASET_{submission_id}/IMAGES/IMAGE_1_.../test.dcm.c4gh",
    #     f"DATASET_{submission_id}/IMAGES/IMAGE_2_.../test2.dcm.c4gh",
    #     f"DATASET_{submission_id}/ANNOTATIONS/test.geojson.c4gh",
    # }

    # Get bearer token from the nbis_client headers
    token = nbis_client._default_headers.get("Authorization", "").replace("Bearer ", "")

    # S3 config is loaded when the service is instantiated, so set these values lazily for this test.
    monkeypatch.setenv("S3_REGION", mock_s3_region)
    endpoint_url = "https://staging-inbox.bp.nbis.se"
    monkeypatch.setenv("S3_ENDPOINT", endpoint_url)
    # Public BP key
    monkeypatch.setenv(
        "CRYPT4GH_PUBLIC_KEY",
        "LS0tLS1CRUdJTiBDUllQVDRHSCBQVUJMSUMgS0VZLS0tLS0KTWExUzVKVW90ZXRsOVdGSVNobU5ncEhMNDBkZG42QmxEelBXbE1oK1puND0KLS0tLS1FTkQgQ1JZUFQ0R0ggUFVCTElDIEtFWS0tLS0tCg==",
    )
    # Private key generated for our testing
    monkeypatch.setenv(
        "CRYPT4GH_PRIVATE_KEY",
        "LS0tLS1CRUdJTiBDUllQVDRHSCBQUklWQVRFIEtFWS0tLS0tCll6Um5hQzEyTVFBR2MyTnllWEIwQUJRQUFBQUF5a1hJVzJJTUhuVS9idllxalFHL2tRQVJZMmhoWTJoaE1qQmZjRzlzZVRFek1EVUFQRTQ0OWsrYldmSGsvM2pmNmYwSm91VTZCaWRma0k2SU1mdDJiaTZNUVp2TWM0WU5jbFpydW5TUmUxT3NiR0ExMnF5eGhISXE3WEJzRjBlQ0JBPT0KLS0tLS1FTkQgQ1JZUFQ0R0ggUFJJVkFURSBLRVktLS0tLQo=",
    )
    monkeypatch.setenv("CRYPT4GH_PRIVATE_KEY_PASSPHRASE", "secret-passphrase")

    s3_inbox = S3InboxSDAService(AsyncMock())
    assert s3_inbox.endpoint == "https://staging-inbox.bp.nbis.se"

    # Upload submission files to S3 inbox in the same way a user would manually before publishing
    user = await get_user_id(nbis_client)
    bucket = user.replace("@", "_")
    for file in filenames:
        await s3_inbox._add_file_to_bucket(bucket, file, bucket, bucket, token, "test content".encode("utf-8"))

    # Publish submission
    await publish_submission(nbis_client, submission_id, no_files=False)


async def assert_immutable_after_publish_sd(client: ClientSession, submission_id: str):
    """Assert that the submission can't be changes after publishing."""

    api_prefix_v1 = deployment_config().API_PREFIX_V1

    # Check that submission can't be changed.
    async with client.patch(
        f"{api_prefix_v1}/submissions/{submission_id}", data=json.dumps({"name": "new_name"})
    ) as resp:
        assert resp.status == 400

    # Check that submission can't be re-published.
    async with client.patch(f"{api_prefix_v1}/publish/{submission_id}") as resp:
        assert resp.status == 400

    # Check that submission can't be deleted.
    async with client.delete(f"{api_prefix_v1}/submissions/{submission_id}") as resp:
        assert resp.status == 400


async def assert_immutable_after_publish_bp(
    client: ClientSession,
    submission_id: str,
    submission_name: str,
    object_names: BigpictureObjectNames,
    is_datacite: bool,
):
    """Assert that the submission can't be changes after publishing."""

    api_prefix_v1 = deployment_config().API_PREFIX_V1

    # Check that submission can't be changed.
    _, _, files = bp_update_documents(submission_name, object_names, is_datacite)
    async with client.patch(f"{api_prefix_v1}/submit/{submission_id}", data=files) as resp:
        assert resp.status == 400

    # Check that submission can't be re-published.
    async with client.patch(f"{api_prefix_v1}/publish/{submission_id}") as resp:
        assert resp.status == 400

    # Check that submission can't be deleted.
    async with client.delete(f"{api_prefix_v1}/submit/{submission_id}") as resp:
        assert resp.status == 400
