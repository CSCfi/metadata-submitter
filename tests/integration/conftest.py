"""Integration test fixtures.

Setting scope to `class` means that tests should be grouped in classes
to share functionality of the `class` scoped fixtures.
"""

import logging
import os
import uuid
from typing import Any, AsyncGenerator
from urllib.parse import urlencode

import aiohttp
import pytest
from dotenv import dotenv_values
from yarl import URL

from tests.integration.conf import (
    base_url,
    mock_auth_url,
    mock_s3_region,
    other_test_user,
    other_test_user_family,
    other_test_user_given,
)
from tests.integration.helpers import (
    add_bucket,
    add_file_to_bucket,
    delete_bucket,
    delete_submission,
    post_submission,
)

LOG = logging.getLogger(__name__)
LOG.setLevel(logging.DEBUG)


def pytest_addoption(parser):
    """Add command line options."""
    parser.addoption(
        "--nocleanup",
        action="store_true",
        default=False,
        help="run tests without any cleanup",
    )


@pytest.fixture
def secret_env(monkeypatch):
    base_dir = os.path.dirname(__file__)
    dotenv_path = os.path.join(base_dir, ".env.secret")
    if not os.path.exists(dotenv_path):
        pytest.fail(f"{dotenv_path} does not exist")

    for k, v in dotenv_values(dotenv_path).items():
        monkeypatch.setenv(k, v)
    yield


@pytest.fixture
async def submission_factory(client_logged_in: aiohttp.ClientSession, project_id: str):
    default_project_id = project_id
    submissions_ids = []

    async def _create_submission(
        workflow: str,
        *,
        name: str | None = None,
        project_id: str | None = None,
        submission: dict[str, Any] | None = None,
    ):  # noqa
        if name is None:
            name = f"name_{uuid.uuid4()}"

        title = f"test submission for {workflow} workflow"
        description = f"test submission for {workflow} workflow"

        if not submission:
            submission = {
                "name": name,
                "title": title,
                "description": description,
                "projectId": project_id or default_project_id,
                "workflow": workflow,
            }
        else:
            submission["name"] = name
            submission["title"] = title
            submission["description"] = description
            submission["projectId"] = project_id or default_project_id
            submission["workflow"] = workflow

        submission_id = await post_submission(client_logged_in, submission)
        submissions_ids.append(submission_id)
        return submission_id, submission

    yield _create_submission

    for submission_id in submissions_ids:
        await delete_submission(
            client_logged_in, submission_id, ignore_published_error=True, ignore_not_found_error=True
        )


@pytest.fixture(name="client")
async def fixture_client() -> AsyncGenerator[aiohttp.ClientSession]:
    """Get an HTTP client without JWT authentication."""
    async with aiohttp.ClientSession() as client:
        yield client


@pytest.fixture(name="client_logged_in")
async def fixture_client_logged_in() -> AsyncGenerator[aiohttp.ClientSession]:
    """Create client by using the OIDC standard authentication flow."""

    async with aiohttp.ClientSession() as client:
        params = {
            "sub": other_test_user,
            "family": other_test_user_family,
            "given": other_test_user_given,
        }

        # Set mock user in the mock auth service.
        await client.get(f"{mock_auth_url}/setmock?{urlencode(params)}")

        # Start OIDC authentication.
        async with client.get(f"{base_url}/aai", allow_redirects=False) as resp:
            assert resp.status in (302, 303)
            first_redirect = resp.headers["Location"]

            # Follow the first redirect to OIDC /authorize.
            async with client.get(first_redirect, allow_redirects=False) as second_resp:
                assert resp.status in (302, 303)
                second_redirect = second_resp.headers["Location"]

                # Follow the second redirect to API /callback.
                async with client.get(second_redirect, allow_redirects=False) as third_resp:
                    assert resp.status in (302, 303)

                    # Extract the JWT token from the cookie.
                    cookies = third_resp.cookies
                    access_token = cookies.get("access_token").value

        # Add the JWT token in the cookie.
        client.cookie_jar.update_cookies({"access_token": access_token}, response_url=URL(base_url))
        # client.headers["Authorization"] = f"Bearer {token}"

        yield client


@pytest.fixture(name="user_id")
async def fixture_user_id() -> str:
    """Return the user id for the default authenticated user."""
    return other_test_user


@pytest.fixture(name="project_id")
async def fixture_project_id() -> str:
    """Return the first project id for the authenticated user."""
    return "1000"


@pytest.fixture(name="project_id_2")
async def fixture_project_id_2() -> str:
    """Return the second project id for the authenticated user."""
    return "2000"


@pytest.fixture(name="mock_pouta_token")
async def fixture_mock_pouta_token(client) -> str:
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
