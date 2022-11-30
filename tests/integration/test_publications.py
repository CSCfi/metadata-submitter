"""Smoke test publications."""
import logging

from tests.integration.conf import objects_url, submissions_url
from tests.integration.helpers import (
    create_request_json_data,
    post_object_json,
    publish_submission,
    put_submission_doi,
    put_submission_rems,
)

LOG = logging.getLogger(__name__)
LOG.setLevel(logging.DEBUG)


class TestMinimalJsonPublication:
    """Test minimal publication."""

    async def test_minimal_fega_json_publication(self, client_logged_in, submission_fega):
        """Test minimal publication workflow with json submissions.

        :param client_logged_in: HTTP client in which request call is made
        :param submission_fega: submission ID, created with the fega workflow
        """
        await post_object_json(client_logged_in, "study", submission_fega, "SRP000539.json")
        doi_data_raw = await create_request_json_data("doi", "test_doi.json")
        await put_submission_doi(client_logged_in, submission_fega, doi_data_raw)
        rems_data = await create_request_json_data("dac", "dac_rems.json")
        await put_submission_rems(client_logged_in, submission_fega, rems_data)

        await publish_submission(client_logged_in, submission_fega)

        async with client_logged_in.get(f"{submissions_url}/{submission_fega}") as resp:
            LOG.debug(f"Checking that submission {submission_fega} was published")
            res = await resp.json()
            assert res["submissionId"] == submission_fega, "expected submission id does not match"
            assert res["published"] is True, "submission is published, expected False"


class TestMinimalJsonPublicationRems:
    """Test minimal publication."""

    async def test_minimal_fega_json_publication_rems(self, client_logged_in, submission_fega):
        """Test minimal publication workflow with json submissions.

        :param client_logged_in: HTTP client in which request call is made
        :param submission_fega: submission ID, created with the fega workflow
        """
        await post_object_json(client_logged_in, "study", submission_fega, "SRP000539.json")
        ds_id = await post_object_json(client_logged_in, "dataset", submission_fega, "dataset.json")
        await post_object_json(client_logged_in, "run", submission_fega, "ERR000076.json")

        doi_data_raw = await create_request_json_data("doi", "test_doi.json")
        await put_submission_doi(client_logged_in, submission_fega, doi_data_raw)

        rems_data = await create_request_json_data("dac", "dac_rems.json")
        await put_submission_rems(client_logged_in, submission_fega, rems_data)

        await publish_submission(client_logged_in, submission_fega)

        async with client_logged_in.get(f"{submissions_url}/{submission_fega}") as resp:
            LOG.debug(f"Checking that submission {submission_fega} was published")
            res = await resp.json()
            assert res["submissionId"] == submission_fega, "expected submission id does not match"
            assert res["published"] is True, "submission is published, expected False"

        async with client_logged_in.get(f"{objects_url}/dataset/{ds_id}?submission_fega={submission_fega}") as resp:
            LOG.debug(f"Checking that dataset {ds_id} in submission {submission_fega} has rems data")
            res = await resp.json()
            assert res["accessionId"] == ds_id, "expected dataset id does not match"
            assert "rems" in res, "expected rems field not found in dataset"
            assert res["rems"]["workflowId"] == 1, "expected workflowId does not match"
            assert res["rems"]["organizationId"] == "CSC", "expected organizationId does not match"
            assert "resourceId" in res["rems"], "expected resourceId not found in rems field"
            assert "catalogueId" in res["rems"], "expected catalogueId not found in rems field"
