"""Integration test fixtures.

Setting scope to `class` means that tests should be grouped in classes
to share functionality of the `class` scoped fixtures.
"""

import logging
import os
import uuid
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Awaitable, Protocol

import aiohttp
import pytest
from dotenv import dotenv_values
from yarl import URL

from metadata_backend.api.json import to_json_dict
from metadata_backend.api.models.submission import Submission
from tests.integration.conf import (
    auth_url,
    base_url,
    mock_s3_region,
    mock_user,
    nbis_base_url,
    submissions_url,
    submit_url,
)
from tests.integration.helpers import (
    add_bucket,
    add_file_to_bucket,
    delete_bucket,
    get_submission,
)
from tests.utils import bp_submission_documents, bp_update_documents, sd_submission_document

LOG = logging.getLogger(__name__)
LOG.setLevel(logging.DEBUG)


@pytest.fixture
def secret_env(monkeypatch):
    base_dir = os.path.dirname(__file__)
    dotenv_path = os.path.join(base_dir, ".env.secret")
    if not os.path.exists(dotenv_path):
        pytest.fail(f"{dotenv_path} does not exist")

    for k, v in dotenv_values(dotenv_path).items():
        monkeypatch.setenv(k, v)
    yield


class SubmissionCallableSD(Protocol):
    def __call__(
        self, submission_dict: dict[str, Any] | None = None, *, submit_endpoint: bool = False
    ) -> Awaitable[Submission]: ...


class SubmissionUpdateCallableSD(Protocol):
    def __call__(
        self, submission_id: str, submission_dict: dict[str, Any], *, submit_endpoint: bool = False
    ) -> Awaitable[Submission]: ...


@pytest.fixture
async def sd_submission(sd_client: aiohttp.ClientSession, project_id: str) -> SubmissionCallableSD:
    """
    Create SD submission using the /submission or /submit endpoint.

    Uses the provided submission object, or creates a submission with
    minimum information. Deletes any existing submission with the same
    name.
    """

    async def _create(submission_dict: dict[str, Any] | None = None, *, submit_endpoint: bool = False) -> Submission:
        if not submission_dict:
            submission = Submission(
                name=f"name_{uuid.uuid4()}",
                title=f"title_{uuid.uuid4()}",
                description=f"description_{uuid.uuid4()}",
                projectId=project_id,
            )
        else:
            submission_dict["projectId"] = project_id
            submission = Submission.model_validate(submission_dict)

        # Delete submission if it exists (requires ALLOW_UNSAFE=TRUE).
        # Delete by name is only supported by the new /submit endpoint.
        async with sd_client.delete(
            f"{submit_url}/{submission.name}?projectId={submission.projectId}&unsafe=true",
        ) as resp:
            data = resp.content
            assert resp.status == 204

        # Post submission.
        if submit_endpoint:
            data = sd_submission_document(submission)
            async with sd_client.post(f"{submit_url}?projectId={project_id}", data=data) as resp:
                data = await resp.json()
                assert resp.status == 200
                submission_id = data["submissionId"]
                return await get_submission(sd_client, submission_id)
        else:
            async with sd_client.post(f"{submissions_url}", json=to_json_dict(submission)) as resp:
                data = await resp.json()
                assert resp.status == 201
                submission_id = data["submissionId"]
                return await get_submission(sd_client, submission_id)

    return _create


@pytest.fixture
async def sd_submission_update(sd_client: aiohttp.ClientSession, project_id: str) -> SubmissionUpdateCallableSD:
    """Update SD submission using the /submission or /submit endpoint."""

    async def _update(
        submission_id: str, submission_dict: dict[str, Any], *, submit_endpoint: bool = False
    ) -> Submission:
        # Patch submission.
        if submit_endpoint:
            data = sd_submission_document(submission_dict)
            async with sd_client.patch(f"{submit_url}/{submission_id}?projectId={project_id}", data=data) as resp:
                assert resp.status == 200
                return await get_submission(sd_client, submission_id)
        else:
            async with sd_client.patch(f"{submissions_url}/{submission_id}", json=submission_dict) as resp:
                data = await resp.json()
                assert resp.status == 200
                submission_id = data["submissionId"]
                return await get_submission(sd_client, submission_id)

    return _update


class SubmissionCallableBigPicture(Protocol):
    def __call__(
        self, is_datacite: bool
    ) -> Awaitable[tuple[Submission, dict[str, dict[str]]]]: ...  # submission names, object names


class SubmissionUpdateCallableBigPicture(Protocol):
    def __call__(
        self, submission_id: str, submission_name: str, object_names: dict[str, dict[str]], is_datacite: bool
    ) -> Awaitable[Submission]: ...


@pytest.fixture
async def bp_submission(nbis_client: aiohttp.ClientSession, project_id: str) -> SubmissionCallableBigPicture:
    """Create BigPicture submission using the /submit endpoint."""

    async def _create(is_datacite: bool = False) -> tuple[Submission, dict[str, dict[str]]]:  # noqa
        submission_name, object_names, files = bp_submission_documents(is_datacite=is_datacite)

        # Post submission.
        async with nbis_client.post(f"{submit_url}", data=files) as resp:
            data = await resp.json()
            assert resp.status == 200
            return Submission.model_validate(data), object_names

    return _create


@pytest.fixture
async def bp_submission_update(
    nbis_client: aiohttp.ClientSession, project_id: str
) -> SubmissionUpdateCallableBigPicture:
    """
    Update BigPicture submission using the /submit endpoint.

    Uses the same XMLs as the initial submission.
    """

    async def _update(
        submission_id: str, submission_name: str, object_names: dict[str, dict[str, dict[str, str]]], is_datacite: bool
    ) -> Submission:  # noqa
        _, _, files = bp_update_documents(submission_name, object_names, is_datacite)

        # Patch submission.
        async with nbis_client.patch(f"{submit_url}/{submission_id}", data=files) as resp:
            assert resp.status == 200
            return await get_submission(nbis_client, submission_id)

    return _update


@pytest.fixture(name="client")
async def client() -> AsyncGenerator[aiohttp.ClientSession]:
    """Create a HTTP client."""
    async with aiohttp.ClientSession() as client:
        yield client


@asynccontextmanager
async def _oidc_authenticated_client(api_base_url: str) -> AsyncGenerator[aiohttp.ClientSession]:
    """Create an authenticated client using the OIDC standard authentication flow."""

    async with aiohttp.ClientSession(base_url=f"{api_base_url}/") as client:
        # Start OIDC authentication.
        async with client.get("/login", allow_redirects=False) as resp:
            assert resp.status in (302, 303)

        authorize_redirect = resp.headers["Location"]

        # Replace "mockauth" hostname with "localhost" if not in CI/CD environment
        if os.getenv("CICD") != "true":
            authorize_redirect = authorize_redirect.replace("mockauth", "localhost")

        # Follow the first redirect to OIDC /authorize.
        async with client.get(authorize_redirect, allow_redirects=False) as resp:
            assert resp.status in (302, 303)
            callback_redirect = resp.headers["Location"]

        # Follow the second redirect to API /callback.
        async with client.get(callback_redirect, allow_redirects=False) as resp:
            cookies = resp.cookies
            access_token = cookies.get("access_token").value

        # Add the JWT token in the cookie.
        client.cookie_jar.update_cookies({"access_token": access_token}, response_url=URL(api_base_url))

        yield client


@pytest.fixture
async def sd_client() -> AsyncGenerator[aiohttp.ClientSession]:
    """Create CSC submission client using the OIDC standard authentication flow."""

    async with _oidc_authenticated_client(base_url) as client:
        yield client


@pytest.fixture
async def nbis_client() -> AsyncGenerator[aiohttp.ClientSession]:
    """Create NBIS BigPicture submission client using the OIDC standard authentication flow."""

    async with _oidc_authenticated_client(nbis_base_url) as client:
        yield client


@pytest.fixture
async def user_id() -> str:
    """Return the user id for the mock user."""
    return mock_user


@pytest.fixture
async def project_id() -> str:
    """Return the project id for the mock user."""
    return "1000"


@pytest.fixture
async def mock_pouta_token(client) -> str:
    """Return a mock pouta access token for testing Keystone service."""
    async with client.get(f"{auth_url}/userinfo") as resp:
        userinfo = await resp.json()
        return userinfo["pouta_access_token"]


@pytest.fixture
async def s3_manager(secret_env):
    """Fixture to provide S3 management helpers for tests using .env.secret credentials."""

    # Buckets/files should be created for test user robot account
    access_key = os.getenv("USER_S3_ACCESS_KEY_ID")
    secret_key = os.getenv("USER_S3_SECRET_ACCESS_KEY")
    endpoint_url = os.getenv("S3_ENDPOINT")

    class S3Manager:
        async def add_bucket(self, bucket_name):
            await add_bucket(bucket_name, access_key, secret_key, endpoint_url, mock_s3_region)

        async def add_file_to_bucket(self, bucket_name, file_name):
            await add_file_to_bucket(bucket_name, file_name, access_key, secret_key, endpoint_url, mock_s3_region)

        async def delete_bucket(self, bucket_name):
            await delete_bucket(bucket_name, access_key, secret_key, endpoint_url, mock_s3_region)

    manager = S3Manager()
    yield manager
