"""Integration test fixtures.

Setting scope to `class` means that tests should be grouped in classes
to share functionality of the `class` scoped fixtures.
"""

import logging
import uuid
from typing import AsyncGenerator
from urllib.parse import urlencode

import aiohttp
import pytest
from yarl import URL

from tests.integration.conf import (
    base_url,
    metax_url,
    mock_auth_url,
    other_test_user,
    other_test_user_family,
    other_test_user_given,
)
from tests.integration.helpers import (
    add_file_to_folder,
    add_folder,
    delete_file_from_folder,
    delete_folder,
    delete_submission,
    list_files_in_folder,
    list_folders,
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


# Submission factory


@pytest.fixture
async def submission_factory(client_logged_in: aiohttp.ClientSession, project_id: str):
    default_project_id = project_id
    submissions_ids = []

    async def _create_submission(workflow: str, *, name: str | None = None, project_id: str | None = None):  # noqa
        if name is None:
            name = f"name_{uuid.uuid4()}"
        submission = {
            "name": name,
            "title": f"test submission for {workflow} workflow",
            "description": f"test submission for {workflow} workflow",
            "projectId": project_id or default_project_id,
            "workflow": workflow,
        }
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


@pytest.fixture(name="clear_cache", autouse=True)
async def fixture_clear_cache(client):
    """Clear mock metax cache before and after each scoped test."""
    await client.post(f"{metax_url}/purge")
    yield
    await client.post(f"{metax_url}/purge")


@pytest.fixture
async def s3_manager():
    """Fixture to track and cleanup mock S3 folders/files before and after each test."""
    # Ensure mock S3 instance is empty before test
    folders_to_delete = await list_folders()
    for folder_name in folders_to_delete:
        try:
            files_in_folder = await list_files_in_folder(folder_name)
            for file_name in files_in_folder:
                try:
                    await delete_file_from_folder(folder_name, file_name)
                except Exception:
                    pass
            await delete_folder(folder_name)
        except Exception:
            pass

    folders = set()
    files = []

    class S3Manager:
        async def add_folder(self, folder_name):
            await add_folder(folder_name)
            folders.add(folder_name)

        async def add_file_to_folder(self, folder_name, file_name):
            await add_file_to_folder(folder_name, file_name)
            files.append((folder_name, file_name))
            folders.add(folder_name)

        async def delete_file_from_folder(self, folder_name, file_name):
            await delete_file_from_folder(folder_name, file_name)
            if (folder_name, file_name) in files:
                files.remove((folder_name, file_name))

        async def delete_folder(self, folder_name):
            await delete_folder(folder_name)
            folders.discard(folder_name)

    manager = S3Manager()
    yield manager

    # Teardown: remove files and then folders
    for folder_name, file_name in files:
        try:
            await delete_file_from_folder(folder_name, file_name)
        except Exception:
            pass
    for folder_name in folders:
        try:
            await delete_folder(folder_name)
        except Exception:
            pass
