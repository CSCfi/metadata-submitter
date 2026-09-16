"""Test operations with the sync endpoints."""

import io
import logging
import zipfile
from datetime import timedelta

from lxml.etree import QName

from metadata_backend.api.models.sync import SyncSubmissions
from metadata_backend.api.processors.xml.datacite import DATACITE_SCHEMA
from metadata_backend.api.processors.xml.processors import XmlProcessor
from metadata_backend.api.services.bigpicture import BP_SYNC_METADATA_DIR
from metadata_backend.conf.deployment import deployment_config
from tests.integration.conf import nbis_base_url
from tests.integration.conftest import sync_signing_claims
from tests.integration.helpers import publish_submission
from tests.sync import sign_sync_token, sync_claims, sync_key_pair

# The metadata objects of each document of the archive. One document per schema, holding
# every object of that schema: the sample schema carries five object types, so its document
# holds them all.
EXPECTED_OBJECTS: dict[str, list[str]] = {
    "annotation": ["ANNOTATION"],
    "dataset": ["DATASET"],
    "image": ["IMAGE"],
    "landing_page": ["LANDING_PAGE"],
    "observation": ["OBSERVATION"],
    "observer": ["OBSERVER"],
    "organisation": ["ORGANISATION"],
    "policy": ["POLICY"],
    "rems": ["REMS"],
    "sample": ["BIOLOGICAL_BEING", "BLOCK", "CASE", "SLIDE", "SPECIMEN"],
    "staining": ["STAINING"],
}

EXPECTED_DATACITE = f"{BP_SYNC_METADATA_DIR}/{DATACITE_SCHEMA}.xml"
EXPECTED_DATACITE_ROOT = "resource"

LOG = logging.getLogger(__name__)
LOG.setLevel(logging.DEBUG)


async def _read_published_submissions(sync_client, **params: str) -> SyncSubmissions:
    """Read the published submissions the sync endpoint returns."""

    api_prefix_sync = deployment_config().API_PREFIX_SYNC

    async with sync_client.get(f"{api_prefix_sync}", params=params) as resp:
        assert resp.status == 200, await resp.text()
        return SyncSubmissions.model_validate(await resp.json())


async def test_sync_bp(nbis_client, sync_client, bp_submission):
    """Test listing a published submission and reading its metadata objects."""

    api_prefix_sync = deployment_config().API_PREFIX_SYNC

    # Create submission.
    submission, _ = await bp_submission(is_datacite=True)
    submission_id = submission.submissionId

    # An unpublished submission is not synced.
    submissions = await _read_published_submissions(sync_client)
    assert submission_id not in [s.submissionId for s in submissions.submissions]

    async with sync_client.get(f"{api_prefix_sync}/{submission_id}") as resp:
        assert resp.status == 404

    # Publish submission.
    await publish_submission(nbis_client, submission_id, no_files=True)

    # A published submission is synced.
    submissions = await _read_published_submissions(sync_client)
    published = {s.submissionId: s.published for s in submissions.submissions}
    assert submission_id in published

    # Most recently published last.
    dates = [s.published for s in submissions.submissions]
    assert dates == sorted(dates)

    # Published within the period.
    since = published[submission_id] - timedelta(seconds=1)
    submissions = await _read_published_submissions(sync_client, publishedStart=since.isoformat())
    assert submission_id in [s.submissionId for s in submissions.submissions]

    # Published before the period.
    until = published[submission_id] + timedelta(seconds=1)
    submissions = await _read_published_submissions(sync_client, publishedStart=until.isoformat())
    assert submission_id not in [s.submissionId for s in submissions.submissions]

    # Read the metadata objects of the submission.
    async with sync_client.get(f"{api_prefix_sync}/{submission_id}") as resp:
        assert resp.status == 200
        assert resp.headers["Content-Type"] == "application/zip"
        archive = await resp.read()

    with zipfile.ZipFile(io.BytesIO(archive)) as zip_file:
        assert sorted(zip_file.namelist()) == sorted(
            [f"{BP_SYNC_METADATA_DIR}/{schema}.xml" for schema in EXPECTED_OBJECTS] + [EXPECTED_DATACITE]
        )

        for schema, expected in EXPECTED_OBJECTS.items():
            root = XmlProcessor.parse_xml(zip_file.read(f"{BP_SYNC_METADATA_DIR}/{schema}.xml")).getroot()
            assert QName(root.tag).localname == f"{schema.upper()}_SET"
            assert sorted({QName(child.tag).localname for child in root}) == expected

        datacite = XmlProcessor.parse_xml(zip_file.read(EXPECTED_DATACITE)).getroot()
        assert QName(datacite.tag).localname == EXPECTED_DATACITE_ROOT


async def test_sync_without_token(client):
    """Test that the sync endpoints require the sync service token."""

    api_prefix_sync = deployment_config().API_PREFIX_SYNC

    async with client.get(f"{nbis_base_url}{api_prefix_sync}") as resp:
        assert resp.status == 401

    claims = sync_claims(*sync_signing_claims())
    token = sign_sync_token(claims, sync_key_pair()[0])
    async with client.get(
        f"{nbis_base_url}{api_prefix_sync}",
        headers={"Authorization": f"Bearer {token}"},
    ) as resp:
        assert resp.status == 401
