"""Integration test fixtures.

Setting scope to `class` means that tests should be grouped in classes
to share functionality of the `class` scoped fixtures.
"""
import asyncio
import logging
from urllib.parse import urlencode

import aiohttp
import pytest

from tests.integration.conf import (
    AUTHDB,
    DATABASE,
    HOST,
    TLS,
    base_url,
    metax_url,
    mock_auth_url,
    other_test_user,
    other_test_user_family,
    other_test_user_given,
)
from tests.integration.helpers import delete_submission, get_user_data, post_submission
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


@pytest.fixture(scope="session")
def event_loop():
    """Override `event_loop` with a different scope. default is `function`.

    https://github.com/pytest-dev/pytest-asyncio#fixtures
    """
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session", name="client")
async def fixture_client():
    """Reusable aiohttp client."""
    async with aiohttp.ClientSession() as client:
        yield client


@pytest.fixture(scope="class", name="client_logged_in")
async def fixture_client_logged_in():
    """Reusable aiohttp client with credentials."""
    async with aiohttp.ClientSession() as client:
        params = {
            "sub": other_test_user,
            "family": other_test_user_family,
            "given": other_test_user_given,
        }

        await client.get(f"{mock_auth_url}/setmock?{urlencode(params)}")
        await client.get(f"{base_url}/aai")
        yield client


@pytest.fixture(scope="class", name="project_id")
async def fixture_project_id(client_logged_in: aiohttp.ClientSession):
    """Get a project_id for the current session."""
    user_data = await get_user_data(client_logged_in)
    return user_data["projects"][0]["projectId"]


async def make_submission(client_logged_in: aiohttp.ClientSession, project_id: str, workflow: str):
    """Create a submission to be reused across tests."""
    submission = {
        "name": "submission test 1",
        "description": "submission test submission 1",
        "projectId": project_id,
        "workflow": workflow,
    }
    submission_id = await post_submission(client_logged_in, submission)

    return submission_id


@pytest.fixture(scope="class", name="submission_fega")
async def fixture_submission_fega(client_logged_in: aiohttp.ClientSession, project_id: str):
    """Create a FEGA submission to be reused across tests that are grouped under the same scope."""
    submission_id = await make_submission(client_logged_in, project_id, "FEGA")
    yield submission_id

    try:
        await delete_submission(client_logged_in, submission_id)
    except AssertionError:
        # Published submissions can't be deleted
        LOG.debug("Attempted to delete %r, which failed", submission_id)


@pytest.fixture(scope="class", name="submission_bigpicture")
async def fixture_submission_bigpicture(client_logged_in: aiohttp.ClientSession, project_id: str):
    """Create a BigPicture submission to be reused across tests that are grouped under the same scope."""
    submission_id = await make_submission(client_logged_in, project_id, "BigPicture")
    yield submission_id

    try:
        await delete_submission(client_logged_in, submission_id)
    except AssertionError:
        # Published submissions can't be deleted
        LOG.debug("Attempted to delete %r, which failed", submission_id)


@pytest.fixture(scope="session", name="mongo")
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


@pytest.fixture(scope="class", name="database")
def fixture_database(mongo):
    """Database client."""
    return mongo.db


@pytest.fixture(scope="class", name="recreate_db", autouse=True)
async def fixture_recreate_db(request, mongo):
    """Recreate the schema after each scoped test."""
    if not request.config.getoption("--nocleanup"):
        await mongo.recreate_db()


@pytest.fixture(scope="class", name="clear_cache", autouse=True)
async def fixture_clear_cache(client):
    """Clear mock metax cache before and after each scoped test."""
    await client.post(f"{metax_url}/purge")
    yield
    await client.post(f"{metax_url}/purge")
