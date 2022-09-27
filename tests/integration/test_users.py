"""Test operations with users."""
import logging

import aiohttp

from tests.integration.conf import (
    other_test_user,
    other_test_user_family,
    other_test_user_given,
    submissions_url,
    templates_url,
    test_user,
    test_user_family,
    test_user_given,
    user_id,
    users_url,
)
from tests.integration.helpers import (
    create_request_json_data,
    delete_submission,
    delete_template,
    delete_user,
    get_templates,
    get_user_data,
    login,
    patch_template,
    post_object,
    post_object_json,
    post_submission,
    post_template_json,
    publish_submission,
    put_submission_dac,
    put_submission_doi,
)

LOG = logging.getLogger(__name__)
LOG.setLevel(logging.DEBUG)


class TestUsers:
    """Test user operations."""

    async def test_token_auth(self, client_logged_in):
        """Test token auth."""
        async with aiohttp.ClientSession() as sess:
            headers = {"Authorization": "Bearer test"}
            user_data = await get_user_data(sess, headers=headers)
            assert user_data["name"] == "Mock Family"
            assert user_data["projects"][0]["projectNumber"] == "1000"
            assert user_data["projects"][0]["projectOrigin"] == "csc"
            assert user_data["projects"][5]["projectNumber"] == "test_namespace:test_root:group3"
            assert user_data["projects"][5]["projectOrigin"] == "lifescience"

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
            LOG.debug(f"Reading user {user_id}")
            assert resp.status == 200, f"HTTP Status code error, got {resp.status}"

        # Add user to client and create a patch to add submission to user
        submission_not_published = {
            "name": "Mock User Submission",
            "description": "Mock submission for testing users",
            "projectId": project_id,
        }
        submission_id = await post_submission(client_logged_in, submission_not_published)

        async with client_logged_in.get(f"{submissions_url}/{submission_id}?projectId={project_id}") as resp:
            LOG.debug(f"Checking that submission {submission_id} was added")
            res = await resp.json()
            assert res["name"] == submission_not_published["name"]
            assert res["projectId"] == submission_not_published["projectId"]

        submission_published = {
            "name": "Another test Submission",
            "description": "Test published submission does not get deleted",
            "projectId": project_id,
        }
        publish_submission_id = await post_submission(client_logged_in, submission_published)

        # Add DOI for publishing the submission
        doi_data_raw = await create_request_json_data("doi", "test_doi.json")
        await put_submission_doi(client_logged_in, publish_submission_id, doi_data_raw)

        dac_data = await create_request_json_data("dac", "dac_rems.json")
        await put_submission_dac(client_logged_in, publish_submission_id, dac_data)

        # add a study and dataset for publishing a submission
        await post_object_json(client_logged_in, "study", publish_submission_id, "SRP000539.json")
        await post_object(client_logged_in, "dataset", publish_submission_id, "dataset.xml")

        await publish_submission(client_logged_in, publish_submission_id)
        async with client_logged_in.get(f"{submissions_url}/{publish_submission_id}?projectId={project_id}") as resp:
            LOG.debug(f"Checking that submission {publish_submission_id} was published")
            res = await resp.json()
            assert res["published"] is True, "submission is not published, expected True"

        submission_not_published = {
            "name": "Delete Submission",
            "description": "Mock submission to delete while testing users",
            "projectId": project_id,
        }
        delete_submission_id = await post_submission(client_logged_in, submission_not_published)
        async with client_logged_in.get(f"{submissions_url}/{delete_submission_id}?projectId={project_id}") as resp:
            LOG.debug(f"Checking that submission {delete_submission_id} was added")
            res = await resp.json()
            assert res["name"] == submission_not_published["name"]
            assert res["projectId"] == submission_not_published["projectId"]
        await delete_submission(client_logged_in, delete_submission_id)
        async with client_logged_in.get(f"{submissions_url}/{delete_submission_id}?projectId={project_id}") as resp:
            LOG.debug(f"Checking that submission {delete_submission_id} was deleted")
            assert resp.status == 404

        template_id = await post_template_json(client_logged_in, "study", "SRP000539_template.json", project_id)
        await patch_template(client_logged_in, "study", template_id, "patch.json")
        async with client_logged_in.get(f"{templates_url}/study/{template_id}") as resp:
            LOG.debug(f"Checking that template: {template_id} was added")
            res = await resp.json()
            assert res["accessionId"] == template_id
            assert res["projectId"] == project_id
            assert res["identifiers"]["primaryId"] == "SRP000539"

        async with client_logged_in.get(f"{templates_url}?projectId={project_id}") as resp:
            LOG.debug("Checking that template display title was updated in separate templates list")
            res = await resp.json()
            assert res[0]["tags"]["displayTitle"] == "new name"

        await delete_template(client_logged_in, "study", template_id)
        async with client_logged_in.get(f"{templates_url}/study/{template_id}") as resp:
            LOG.debug(f"Checking that template {template_id} was deleted")
            assert resp.status == 404

        template_ids = await post_template_json(client_logged_in, "study", "SRP000539_list.json", project_id)
        assert len(template_ids) == 2, "templates could not be added as batch"
        templates = await get_templates(client_logged_in, project_id)

        assert len(templates) == 2, f"should be 2 templates, got {len(templates)}"
        assert templates[0]["schema"] == "template-study", "wrong template schema"

        # Delete user
        await delete_user(client_logged_in, user_id)
        # 401 means API is inaccessible thus client ended
        # this check is not needed but good to do
        async with client_logged_in.get(f"{users_url}/{user_id}") as resp:
            LOG.debug(f"Checking that user {user_id} was deleted")
            assert resp.status == 401, f"HTTP Status code error, got {resp.status}"
