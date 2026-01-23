"""Integration test fixtures.

Setting scope to `class` means that tests should be grouped in classes
to share functionality of the `class` scoped fixtures.
"""

import logging
import os
import re
import uuid
from io import BufferedReader
from typing import Any, AsyncGenerator, Awaitable, Protocol
from urllib.parse import urlencode
from xml.etree import ElementTree

import aiohttp
import pytest
from dotenv import dotenv_values
from yarl import URL

from metadata_backend.api.json import to_json
from metadata_backend.api.models.submission import Submission, SubmissionWorkflow
from tests.integration.conf import (
    TEST_FILES_ROOT,
    base_url,
    mock_auth_url,
    mock_s3_region,
    mock_user,
    mock_user_family_name,
    mock_user_given_name,
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
    workflow = SubmissionWorkflow.SD

    async def _create(submission_dict: dict[str, Any] | None = None, *, submit_endpoint: bool = False) -> Submission:
        if not submission_dict:
            submission = Submission(
                name=f"name_{uuid.uuid4()}",
                title=f"title_{uuid.uuid4()}",
                description=f"description_{uuid.uuid4()}",
                projectId=project_id,
                workflow=workflow,
            )
        else:
            submission_dict["projectId"] = project_id
            submission_dict["workflow"] = workflow
            submission = Submission.model_validate(submission_dict)

        # Delete submission if it exists (requires ALLOW_UNSAFE=TRUE).
        # Delete by name is only supported by the new /submit endpoint.
        async with sd_client.delete(
            f"{submit_url}/{workflow.value}/{submission.name}?projectId={submission.projectId}&unsafe=true",
        ) as resp:
            assert resp.status == 204

        # Post submission.
        if submit_endpoint:
            async with sd_client.post(
                f"{submit_url}/{workflow.value}?projectId={project_id}", data=to_json(submission)
            ) as resp:
                data = await resp.json()
                assert resp.status == 200
                return Submission.model_validate(data)
        else:
            async with sd_client.post(f"{submissions_url}", data=to_json(submission)) as resp:
                data = await resp.json()
                assert resp.status == 201
                submission_id = data["submissionId"]
                return await get_submission(sd_client, submission_id)

    return _create


@pytest.fixture
async def sd_submission_update(sd_client: aiohttp.ClientSession, project_id: str) -> SubmissionUpdateCallableSD:
    """Update SD submission using the /submission or /submit endpoint."""
    workflow = SubmissionWorkflow.SD

    async def _update(
        submission_id: str, submission_dict: dict[str, Any], *, submit_endpoint: bool = False
    ) -> Submission:
        # Patch submission.
        if submit_endpoint:
            async with sd_client.patch(
                f"{submit_url}/{workflow.value}/{submission_id}?projectId={project_id}", json=submission_dict
            ) as resp:
                data = await resp.json()
                assert resp.status == 200
                return Submission.model_validate(data)
        else:
            async with sd_client.patch(f"{submissions_url}/{submission_id}", json=submission_dict) as resp:
                data = await resp.json()
                assert resp.status == 200
                submission_id = data["submissionId"]
                return await get_submission(sd_client, submission_id)

    return _update


class SubmissionCallableBigPicture(Protocol):
    def __call__(
        self,
    ) -> Awaitable[Submission]: ...


class SubmissionUpdateCallableBigPicture(Protocol):
    def __call__(self, submission_id: str) -> Awaitable[Submission]: ...


def bp_submission_data() -> tuple[str, dict[str, BufferedReader]]:
    """Get the BP submission name and XML data for multipart upload."""

    submission_dir = TEST_FILES_ROOT / "xml" / "bigpicture"
    files = [
        "dataset.xml",
        "policy.xml",
        "image.xml",
        "annotation.xml",
        "observation.xml",
        "observer.xml",
        "sample.xml",
        "staining.xml",
        "landing_page.xml",
        "rems.xml",
        "organisation.xml",
        "datacite.xml",
    ]

    # Read XML files.
    data = {}
    for file in files:
        data[file] = (submission_dir / file).open("rb")

    # Read submission name from XML.
    dataset_xml = ElementTree.parse(data["dataset.xml"]).getroot()
    submission_name = [elem.text for elem in dataset_xml.findall(".//SHORT_NAME")][0]
    data["dataset.xml"].seek(0)

    return submission_name, data


def bp_submission_update_data() -> tuple[str, dict[str, BufferedReader]]:
    """Get the BP submission name and XML data for multipart upload."""

    submission_dir = TEST_FILES_ROOT / "xml" / "bigpicture"
    update_dir = TEST_FILES_ROOT / "xml" / "bigpicture" / "update"
    files = [
        "policy.xml",
        "annotation.xml",
        "observation.xml",
        "observer.xml",
        "sample.xml",
        "staining.xml",
        "landing_page.xml",
        "rems.xml",
        "organisation.xml",
        "datacite.xml",
    ]
    updated_files = [
        "dataset.xml",
        "image.xml",
    ]

    # Read XML files.
    data = {}
    for file in files:
        data[file] = (submission_dir / file).open("rb")
    for file in updated_files:
        data[file] = (update_dir / file).open("rb")

    # Read submission name from XML.
    dataset_xml = ElementTree.parse(data["dataset.xml"]).getroot()
    submission_name = [elem.text for elem in dataset_xml.findall(".//SHORT_NAME")][0]
    data["dataset.xml"].seek(0)

    return submission_name, data


@pytest.fixture
async def bp_submission(nbis_client: aiohttp.ClientSession, project_id: str) -> SubmissionCallableBigPicture:
    """
    Create BigPicture NBIS submission using the /submit endpoint.

    Creates a submission using default XMLs. Deletes any existing submission
    with the same name.
    """
    workflow = SubmissionWorkflow.BP

    async def _create() -> Submission:  # noqa
        submission_name, data = bp_submission_data()

        # Delete submission if it exists (requires ALLOW_UNSAFE=TRUE).
        async with nbis_client.delete(
            f"{submit_url}/{workflow.value}/{submission_name}?&unsafe=true",
        ) as resp:
            assert resp.status == 204

        # Post submission.
        async with nbis_client.post(f"{submit_url}/{workflow.value}", data=data) as resp:
            data = await resp.json()
            assert resp.status == 200
            return Submission.model_validate(data)

    return _create


@pytest.fixture
async def bp_submission_update(
    nbis_client: aiohttp.ClientSession, project_id: str
) -> SubmissionUpdateCallableBigPicture:
    """Update BigPicture NBIS submission using the /submit endpoint."""
    workflow = SubmissionWorkflow.BP

    async def _create(submission_id: str) -> Submission:  # noqa
        submission_name, data = bp_submission_update_data()

        # Patch submission.
        async with nbis_client.patch(f"{submit_url}/{workflow.value}/{submission_id}", data=data) as resp:
            data = await resp.json()
            assert resp.status == 200
            return Submission.model_validate(data)

    return _create


@pytest.fixture
async def mock_auth():
    """Configure mock authentication service."""

    async with aiohttp.ClientSession() as client:
        params = {
            "sub": mock_user,
            "family": mock_user_family_name,
            "given": mock_user_given_name,
        }
        await client.get(f"{mock_auth_url}/setmock?{urlencode(params)}")


@pytest.fixture(name="client")
async def client() -> AsyncGenerator[aiohttp.ClientSession]:
    """Create a HTTP client."""
    async with aiohttp.ClientSession() as client:
        yield client


@pytest.fixture
async def sd_client(mock_auth) -> AsyncGenerator[aiohttp.ClientSession]:
    """Create SD submission client using the OIDC standard authentication flow."""

    async with aiohttp.ClientSession(base_url=f"{base_url}/") as client:
        # Start OIDC authentication.
        async with client.get("/login", allow_redirects=False) as resp:
            assert resp.status in (302, 303)
            first_redirect = resp.headers["Location"]

        # Follow the first redirect to OIDC /authorize.
        async with client.get(first_redirect, allow_redirects=False) as resp:
            assert resp.status in (302, 303)
            second_redirect = resp.headers["Location"]

        # Follow the second redirect to API /callback.
        async with client.get(second_redirect, allow_redirects=False) as resp:
            assert resp.status in (302, 303)

            # Extract the JWT token from the cookie.
            cookies = resp.cookies
            access_token = cookies.get("access_token").value

        # Add the JWT token in the cookie.
        client.cookie_jar.update_cookies({"access_token": access_token}, response_url=URL(base_url))

        yield client


@pytest.fixture
async def nbis_client(mock_auth) -> AsyncGenerator[aiohttp.ClientSession]:
    """Create NBIS BigPicture submission client using the OIDC standard authentication flow."""

    async with aiohttp.ClientSession(base_url=f"{nbis_base_url}/") as client:
        # Start OIDC authentication.
        async with client.get("/login", allow_redirects=False) as resp:
            match = re.search(r"Complete the login at:\s*(\S+)", await resp.text())
            redirect_url = match.group(1)
            assert resp.status == 200

        # Follow the redirect to OIDC /authorize.
        async with client.get(redirect_url) as resp:
            assert resp.status == 200

            # Extract the JWT token from the response.
            access_token = await resp.text()

        # Add the JWT token in the cookie.
        client.cookie_jar.update_cookies({"access_token": access_token}, response_url=URL(nbis_base_url))

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
    async with client.get(f"{mock_auth_url}/userinfo") as resp:
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
