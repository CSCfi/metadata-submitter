"""Test operations with users."""

import logging
from hmac import new
from time import time

import aiohttp
import pytest

from metadata_backend.api.services.ldap import get_user_projects, verify_user_project
from tests.integration.conf import (
    other_test_user,
    other_test_user_family,
    other_test_user_given,
    submissions_url,
    test_user,
    test_user_family,
    test_user_given,
    user_id,
    users_url,
    ldap_user_id,
    ldap_project_id,
)
from tests.integration.helpers import (
    create_request_json_data,
    delete_submission,
    delete_user,
    get_user_data,
    login,
    patch_submission_doi,
    patch_submission_rems,
    post_object,
    post_object_json,
    post_submission,
    publish_submission,
)

LOG = logging.getLogger(__name__)
LOG.setLevel(logging.DEBUG)


class TestUsers:
    """Test user operations."""

    async def test_token_auth(self):
        """Test token auth."""
        async with aiohttp.ClientSession() as sess:
            headers = {"Authorization": "Bearer test"}
            user_data = await get_user_data(sess, headers=headers)
            assert user_data["name"] == "Mock Family"
            assert user_data["projects"][0]["projectNumber"] == "1000"
            assert user_data["projects"][0]["projectOrigin"] == "csc"
            assert user_data["projects"][5]["projectNumber"] == "test_namespace:test_root:group3"
            assert user_data["projects"][5]["projectOrigin"] == "lifescience"

    async def test_personal_token(self, client_logged_in):
        """Test that user can create and use a personal token."""
        # generate signing key
        key = ""
        user = ""
        async with client_logged_in.get(f"{users_url}/current/key") as resp:
            res = await resp.json()
            key = res["signingKey"]
            user = res["userId"]
            assert len(key) == 64
            assert len(user) == 32
        # sign token
        msg = str(int(time() + 300)) + user
        token = new(key=key.encode("utf-8"), msg=msg.encode("utf-8"), digestmod="sha256").hexdigest()
        # use token
        headers = {"Authorization": f"Bearer {token}"}
        async with aiohttp.ClientSession() as sess:
            user_data = await get_user_data(sess, headers=headers)
            assert user_data["userId"] == user
            assert user_data["projects"][0]["projectNumber"] == "1000"

    async def test_multiple_user_submissions(self, client_logged_in):
        """Test different users can create a submission."""
        async with aiohttp.ClientSession() as sess:
            await login(sess, other_test_user, other_test_user_given, other_test_user_family)
            user_data = await get_user_data(sess)
            other_test_user_project_id = user_data["projects"][0]["projectId"]

            other_test_user_submission = {
                "name": "submission test 1",
                "description": "submission test submission 1",
                "projectId": other_test_user_project_id,
                "workflow": "FEGA",
            }
            other_test_user_submission_id = await post_submission(sess, other_test_user_submission)

        async with aiohttp.ClientSession() as sess:
            await login(sess, test_user, test_user_given, test_user_family)
            user_data = await get_user_data(sess)
            test_user_project_id = user_data["projects"][0]["projectId"]

            # Test adding and getting objects
            LOG.debug("=== Testing basic CRUD operations ===")
            test_user_submission = {
                "name": "basic test",
                "description": "basic test submission",
                "projectId": test_user_project_id,
                "workflow": "FEGA",
            }
            test_user_submission_id = await post_submission(sess, test_user_submission)

        async with client_logged_in.get(
            f"{submissions_url}/{other_test_user_submission_id}?projectId={other_test_user_project_id}"
        ) as resp:
            res = await resp.json()
            assert res["name"] == other_test_user_submission["name"]
            assert res["projectId"] == other_test_user_submission["projectId"]

        async with client_logged_in.get(
            f"{submissions_url}/{test_user_submission_id}?projectId={test_user_project_id}"
        ) as resp:
            res = await resp.json()
            assert res["name"] == test_user_submission["name"]
            assert res["projectId"] == test_user_submission["projectId"]

    async def test_crud_users_works(self, client_logged_in, project_id):
        """Test users REST API GET, PATCH and DELETE reqs.

        This should be the last test, as it deletes users.

        :param client_logged_in: HTTP client in which request call is made
        :param project_id: id of the project the submission belongs to
        """
        # Check user exists in database (requires an user object to be mocked)
        async with client_logged_in.get(f"{users_url}/{user_id}") as resp:
            LOG.debug("Reading user %s", user_id)
            assert resp.status == 200, f"HTTP Status code error, got {resp.status}"

        # Add user to client and create a patch to add submission to user
        submission_not_published = {
            "name": "Mock User Submission",
            "description": "Mock submission for testing users",
            "projectId": project_id,
            "workflow": "FEGA",
        }
        submission_id = await post_submission(client_logged_in, submission_not_published)

        async with client_logged_in.get(f"{submissions_url}/{submission_id}?projectId={project_id}") as resp:
            LOG.debug("Checking that submission %s was added", submission_id)
            res = await resp.json()
            assert res["name"] == submission_not_published["name"]
            assert res["projectId"] == submission_not_published["projectId"]

        submission_published = {
            "name": "Another test Submission",
            "description": "Test published submission does not get deleted",
            "projectId": project_id,
            "workflow": "FEGA",
        }
        publish_submission_id = await post_submission(client_logged_in, submission_published)

        # Add DOI for publishing the submission
        doi_data_raw = await create_request_json_data("doi", "test_doi.json")
        await patch_submission_doi(client_logged_in, publish_submission_id, doi_data_raw)

        rems_data = await create_request_json_data("dac", "dac_rems.json")
        await patch_submission_rems(client_logged_in, publish_submission_id, rems_data)

        # add a study and dataset for publishing a submission
        await post_object_json(client_logged_in, "study", publish_submission_id, "SRP000539.json")
        await post_object(client_logged_in, "dataset", publish_submission_id, "dataset.xml")
        await post_object_json(client_logged_in, "run", publish_submission_id, "ERR000076.json")
        await post_object_json(client_logged_in, "policy", publish_submission_id, "policy.json")
        await publish_submission(client_logged_in, publish_submission_id)
        async with client_logged_in.get(f"{submissions_url}/{publish_submission_id}?projectId={project_id}") as resp:
            LOG.debug("Checking that submission %s was published", publish_submission_id)
            res = await resp.json()
            assert res["published"] is True, "submission is not published, expected True"

        submission_not_published = {
            "name": "Delete Submission",
            "description": "Mock submission to delete while testing users",
            "projectId": project_id,
            "workflow": "FEGA",
        }
        delete_submission_id = await post_submission(client_logged_in, submission_not_published)
        async with client_logged_in.get(f"{submissions_url}/{delete_submission_id}?projectId={project_id}") as resp:
            LOG.debug("Checking that submission %s was added", delete_submission_id)
            res = await resp.json()
            assert res["name"] == submission_not_published["name"]
            assert res["projectId"] == submission_not_published["projectId"]
        await delete_submission(client_logged_in, delete_submission_id)
        async with client_logged_in.get(f"{submissions_url}/{delete_submission_id}?projectId={project_id}") as resp:
            LOG.debug("Checking that submission %s was deleted", delete_submission_id)
            assert resp.status == 404

        # Delete user
        await delete_user(client_logged_in, user_id)
        # 401 means API is inaccessible thus client ended
        # this check is not needed but good to do
        async with client_logged_in.get(f"{users_url}/{user_id}") as resp:
            LOG.debug("Checking that user %s was deleted", user_id)
            assert resp.status == 401, f"HTTP Status code error, got {resp.status}"


class TestLdap:
    """Test CSC's LDAP service."""

    def test_get_user_projects(self) -> None:
        """Test get user projects."""
        projects = get_user_projects(ldap_user_id)
        assert ldap_project_id in projects, f"Project ID {ldap_project_id} not found in '{ldap_user_id}' user projects"

    def test_verify_user_projects(self) -> None:
        """Test verify user projects."""

        verify_user_project(ldap_user_id, ldap_project_id)

        with pytest.raises(aiohttp.web.HTTPUnauthorized):
            verify_user_project(ldap_user_id, "-1")
