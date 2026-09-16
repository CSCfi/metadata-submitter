"""Test the sync API endpoints."""

from datetime import datetime, timedelta
from pathlib import Path

import pytest
from starlette import status
from starlette.testclient import TestClient

from metadata_backend.api.models.submission import SubmissionWorkflow
from metadata_backend.api.models.sync import SyncSubmissions
from metadata_backend.conf.conf import DEPLOYMENT_NBIS
from metadata_backend.conf.deployment import deployment_config
from metadata_backend.database.postgres.repositories.submission import SubmissionRepository
from metadata_backend.server import create_app
from tests.sync import sign_sync_token, sync_claims, sync_headers
from tests.unit.conftest import TEST_SYNC_AUDIENCE, TEST_SYNC_ISSUER, TEST_SYNC_PRIVATE_KEY
from tests.unit.database.postgres.helpers import create_submission_entity

BP_SUBMISSION_DIR = Path(__file__).parent.parent.parent.parent / "test_files" / "xml" / "bigpicture"


SYNC_HEADERS = sync_headers(sign_sync_token(sync_claims(TEST_SYNC_AUDIENCE, TEST_SYNC_ISSUER), TEST_SYNC_PRIVATE_KEY))


def _sync_url(path: str = "") -> str:
    return f"{deployment_config().API_PREFIX_SYNC}{path}"


def _served_paths(client: TestClient) -> set[str]:
    """The paths the application serves, read from its OpenAPI schema."""

    return set(client.get("/openapi.json").json()["paths"])


def test_sync_routes_no_key(monkeypatch, session):
    monkeypatch.setenv("DEPLOYMENT", DEPLOYMENT_NBIS)
    monkeypatch.setenv("JWT_KEY", "bW9jay1zZWNyZXQtd2hpY2gtaXMtYXQtbGVhc3QtMzItYnl0ZXM=")
    monkeypatch.delenv("SYNC_CLIENTS", raising=False)

    with TestClient(create_app(session)) as client:
        paths = _served_paths(client)

    assert not [path for path in paths if "/sync/" in path]


def test_sync_routes_with_key(nbis_client):
    paths = _served_paths(nbis_client)
    assert _sync_url() in paths
    assert _sync_url("/{submissionId}") in paths


def test_sync_without_key(nbis_client):
    response = nbis_client.get(_sync_url(), params={"publishedStart": "2026-01-01T00:00:00Z"})
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_sync_invalid_key(nbis_client):
    response = nbis_client.get(
        _sync_url(),
        params={"publishedStart": "2026-01-01T00:00:00Z"},
        headers={"Authorization": "invalid"},
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_sync_security(nbis_client):
    """The sync endpoints are documented as requiring the bearer token."""

    schema = nbis_client.get("/openapi.json").json()

    assert "bearerAuth" in schema["components"]["securitySchemes"]
    for path in (_sync_url(), _sync_url("/{submissionId}")):
        assert schema["paths"][path]["get"]["security"] == [{"bearerAuth": []}]


async def _add_published_submission(submission_repository: SubmissionRepository) -> tuple[str, datetime]:
    """A published Bigpicture submission, and the date it was published.

    Published by turning the flag, which is what stamps the date: constructing an entity
    that is published already leaves the date unset, as the flag was never turned.
    """

    entity = create_submission_entity(workflow=SubmissionWorkflow.BP, is_published=False)
    entity.is_published = True
    submission_id = await submission_repository.add_submission(entity)
    return submission_id, entity.published


async def test_sync_no_submissions(nbis_client, submission_repository):
    """A submission published before the period asked for is not returned."""

    _, published = await _add_published_submission(submission_repository)

    response = nbis_client.get(
        _sync_url(),
        params={"publishedStart": (published + timedelta(seconds=1)).isoformat()},
        headers=SYNC_HEADERS,
    )

    assert response.status_code == status.HTTP_200_OK
    assert SyncSubmissions.model_validate(response.json()).submissions == []


async def test_sync_returns_submissions(nbis_client, submission_repository):
    submission_id, published = await _add_published_submission(submission_repository)

    response = nbis_client.get(
        _sync_url(),
        params={"publishedStart": (published - timedelta(seconds=1)).isoformat()},
        headers=SYNC_HEADERS,
    )

    assert response.status_code == status.HTTP_200_OK
    submissions = SyncSubmissions.model_validate(response.json()).submissions
    assert [s.submissionId for s in submissions] == [submission_id]


async def test_sync_published_without_date(nbis_client, submission_repository):
    """A submission published without the date is not returned."""

    entity = create_submission_entity(workflow=SubmissionWorkflow.BP, is_published=True)
    assert entity.published is None
    await submission_repository.add_submission(entity)

    response = nbis_client.get(_sync_url(), headers=SYNC_HEADERS)

    assert response.status_code == status.HTTP_200_OK
    assert SyncSubmissions.model_validate(response.json()).submissions == []


def test_sync_invalid_period(nbis_client):
    response = nbis_client.get(
        _sync_url(),
        params={"publishedStart": "2026-02-01T00:00:00Z", "publishedEnd": "2026-01-01T00:00:00Z"},
        headers=SYNC_HEADERS,
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.parametrize("param", ["publishedStart", "publishedEnd"])
def test_sync_date_without_utc_offset(nbis_client, param):
    """A publication date without a UTC offset is rejected."""

    response = nbis_client.get(_sync_url(), params={param: "2026-01-01T00:00:00"}, headers=SYNC_HEADERS)

    assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_sync_date_with_utc_offset(nbis_client):
    """A publication date with a non-zero UTC offset is accepted."""

    response = nbis_client.get(
        _sync_url(), params={"publishedStart": "2026-01-01T00:00:00+03:00"}, headers=SYNC_HEADERS
    )

    assert response.status_code == status.HTTP_200_OK


def test_sync_invalid_date(nbis_client):
    response = nbis_client.get(_sync_url(), params={"publishedStart": "not a date"}, headers=SYNC_HEADERS)

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json()["detail"] == "Validation error"


def test_sync_unknown_submission(nbis_client):
    response = nbis_client.get(_sync_url("/unknown_submission"), headers=SYNC_HEADERS)
    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_sync_content(nbis_client):
    schema = nbis_client.get("/openapi.json").json()
    responses = schema["paths"][_sync_url("/{submissionId}")]["get"]["responses"]
    assert list(responses[str(status.HTTP_200_OK)]["content"]) == ["application/zip"]
