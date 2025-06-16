"""Integration test fixtures.

Setting scope to `class` means that tests should be grouped in classes
to share functionality of the `class` scoped fixtures.
"""

import logging
from typing import AsyncGenerator
from urllib.parse import urlencode

import aiohttp
import pytest
from yarl import URL

from tests.integration.conf import (
    AUTHDB,
    DATABASE,
    HOST,
    TLS,
    admin_test_user,
    admin_test_user_family,
    admin_test_user_given,
    base_url,
    metax_url,
    mock_auth_url,
    other_test_user,
    other_test_user_family,
    other_test_user_given,
)
from tests.integration.helpers import delete_submission, get_mock_admin_token, post_submission
from tests.integration.mongo import Mongo

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


@pytest.fixture(name="admin_token")
async def fixture_admin_token():
    """Get JWT with admin user credentials used in ingest."""
    async with aiohttp.ClientSession() as client:
        params = {
            "sub": admin_test_user,
            "family": admin_test_user_family,
            "given": admin_test_user_given,
        }

        await client.get(f"{mock_auth_url}/setmock?{urlencode(params)}")
        admin_token = await get_mock_admin_token(client)

        return admin_token


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


async def make_submission(client_logged_in: aiohttp.ClientSession, project_id: str, workflow: str):
    """Create a submission to be reused across tests."""
    submission = {
        "name": f"{workflow} submission test",
        "description": f"test submission for {workflow} workflow",
        "projectId": project_id,
        "workflow": workflow,
    }
    submission_id = await post_submission(client_logged_in, submission)

    return submission_id


@pytest.fixture(name="submission_fega")
async def fixture_submission_fega(client_logged_in: aiohttp.ClientSession, project_id: str):
    """Create a FEGA submission to be reused across tests that are grouped under the same scope."""
    submission_id = await make_submission(client_logged_in, project_id, "FEGA")
    yield submission_id

    try:
        await delete_submission(client_logged_in, submission_id)
    except AssertionError:
        # Published submissions can't be deleted
        LOG.debug("Attempted to delete %r, which failed", submission_id)


@pytest.fixture(name="submission_bigpicture")
async def fixture_submission_bigpicture(client_logged_in: aiohttp.ClientSession, project_id: str):
    """Create a Bigpicture submission to be reused across tests that are grouped under the same scope."""
    submission_id = await make_submission(client_logged_in, project_id, "Bigpicture")
    yield submission_id

    try:
        await delete_submission(client_logged_in, submission_id)
    except AssertionError:
        # Published submissions can't be deleted
        LOG.debug("Attempted to delete %r, which failed", submission_id)


@pytest.fixture(name="submission_sdsx")
async def fixture_submission_sdsx(client_logged_in: aiohttp.ClientSession, project_id: str):
    """Create a SDSX submission to be reused across tests that are grouped under the same scope."""
    submission_id = await make_submission(client_logged_in, project_id, "SDSX")
    yield submission_id

    try:
        await delete_submission(client_logged_in, submission_id)
    except AssertionError:
        # Published submissions can't be deleted
        LOG.debug("Attempted to delete %r, which failed", submission_id)


@pytest.fixture(name="mongo")
async def fixture_mongo(request):
    """Initialize the db, and create a client."""
    if TLS:
        _params = "?tls=true&tlsCAFile=./config/cacert&tlsCertificateKeyFile=./config/combined"
        url = f"mongodb://{AUTHDB}:{AUTHDB}@{HOST}/{DATABASE}{_params}&authSource=admin"
    else:
        url = f"mongodb://{AUTHDB}:{AUTHDB}@{HOST}/{DATABASE}?authSource=admin"

    mongo = Mongo(url)
    await mongo.recreate_db()

    yield mongo

    if not request.config.getoption("--nocleanup"):
        await mongo.drop_db()


@pytest.fixture(name="database")
def fixture_database(mongo):
    """Database client."""
    return mongo.db


@pytest.fixture(name="recreate_db", autouse=True)
async def fixture_recreate_db(request, mongo):
    """Recreate the schema after each scoped test."""
    if not request.config.getoption("--nocleanup"):
        await mongo.recreate_db()


@pytest.fixture(name="clear_cache", autouse=True)
async def fixture_clear_cache(client):
    """Clear mock metax cache before and after each scoped test."""
    await client.post(f"{metax_url}/purge")
    yield
    await client.post(f"{metax_url}/purge")
