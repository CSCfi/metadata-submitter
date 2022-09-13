"""Smoke test publications."""
import logging

from tests.integration.conf import objects_url, submissions_url
from tests.integration.helpers import (
    create_request_json_data,
    post_object_json,
    publish_submission,
    put_submission_dac,
    put_submission_doi,
)

LOG = logging.getLogger(__name__)
LOG.setLevel(logging.DEBUG)


class TestMinimalJsonPublication:
    """Test minimal publication."""

    async def test_minimal_json_publication(self, client_logged_in, submission_id):
        """Test minimal publication workflow with json submissions.

        :param client_logged_in: HTTP client in which request call is made
        :param project_id: id of the project the submission belongs to
        """
        await post_object_json(client_logged_in, "study", submission_id, "SRP000539.json")
        doi_data_raw = await create_request_json_data("doi", "test_doi.json")
        await put_submission_doi(client_logged_in, submission_id, doi_data_raw)
        dac_data = await create_request_json_data("dac", "dac_rems.json")
        await put_submission_dac(client_logged_in, submission_id, dac_data)
        await publish_submission(client_logged_in, submission_id)

        async with client_logged_in.get(f"{submissions_url}/{submission_id}") as resp:
            LOG.debug(f"Checking that submission {submission_id} was published")
            res = await resp.json()
            assert res["submissionId"] == submission_id, "expected submission id does not match"
            assert res["published"] is True, "submission is published, expected False"


class TestMinimalJsonPublicationRems:
    """Test minimal publication."""

    async def test_minimal_json_publication_rems(self, client_logged_in, submission_id):
        """Test minimal publication workflow with json submissions.

        :param client_logged_in: HTTP client in which request call is made
        :param project_id: id of the project the submission belongs to
        """
        await post_object_json(client_logged_in, "study", submission_id, "SRP000539.json")
        ds_id = await post_object_json(client_logged_in, "dataset", submission_id, "dataset.json")

        doi_data_raw = await create_request_json_data("doi", "test_doi.json")
        await put_submission_doi(client_logged_in, submission_id, doi_data_raw)

        dac_data = await create_request_json_data("dac", "dac_rems.json")
        await put_submission_dac(client_logged_in, submission_id, dac_data)

        await publish_submission(client_logged_in, submission_id)

        async with client_logged_in.get(f"{submissions_url}/{submission_id}") as resp:
            LOG.debug(f"Checking that submission {submission_id} was published")
            res = await resp.json()
            assert res["submissionId"] == submission_id, "expected submission id does not match"
            assert res["published"] is True, "submission is published, expected False"

        async with client_logged_in.get(f"{objects_url}/dataset/{ds_id}?submission_id={submission_id}") as resp:
            LOG.debug(f"Checking that dataset {ds_id} in submission {submission_id} has rems data")
            res = await resp.json()
            assert res["accessionId"] == ds_id, "expected dataset id does not match"
            assert "dac" in res
            assert res["dac"]["workflowId"] == 1
            assert res["dac"]["organizationId"] == "CSC"
            assert "resourceId" in res["dac"]
            assert "catalogueId" in res["dac"]
