"""Test operations with draft objects."""

import logging

from tests.integration.conf import drafts_url, test_fega_json_files
from tests.integration.conftest import submission_factory
from tests.integration.helpers import (
    check_object_exists,
    delete_draft,
    patch_draft,
    post_draft,
    put_draft,
)

LOG = logging.getLogger(__name__)
LOG.setLevel(logging.DEBUG)


class TestDrafts:
    """Test operations with draft."""

    async def test_crud_drafts_works(self, client_logged_in, submission_factory):
        """Test drafts REST API POST, PUT and DELETE reqs.

        Tries to create new draft object, gets accession id and checks if correct
        resource is returned with that id. Finally deletes the object and checks it
        was deleted.

        :param client_logged_in: HTTP client in which request call is made
        :param submission_factory: The factory that creates and deletes submissions
        """

        submission_id, _ = await submission_factory("FEGA")

        async def assert_crud_drafts_works(schema, original_file, update_file, pytest=None):
            """Individual tests to be run in parallel."""
            draft_id = await post_draft(client_logged_in, schema, submission_id, original_file)
            await check_object_exists(client_logged_in, schema, draft_id, draft=True)

            assert draft_id == await put_draft(client_logged_in, schema, draft_id, update_file)
            await check_object_exists(client_logged_in, schema, draft_id, draft=True)

            await delete_draft(client_logged_in, schema, draft_id)
            async with client_logged_in.get(f"{drafts_url}/{schema}/{draft_id}") as resp:
                assert resp.status == 404, f"HTTP Status code error, got {resp.status}"

        files = test_fega_json_files + [("sample", "SRS001433.json", "put.json")]
        for schema, original_file, update_file in files:
            await assert_crud_drafts_works(schema, original_file, update_file)

    async def test_patch_drafts_works(self, client_logged_in, submission_factory):
        """Test REST API POST, PATCH and DELETE reqs.

        Tries to create put and patch object, gets accession id and
        checks if correct resource is returned with that id.
        Finally deletes the object and checks it was deleted.
        :param client_logged_in: HTTP client in which request call is made
        :param submission_factory: The factory that creates and deletes submissions
        """

        submission_id, _ = await submission_factory("FEGA")

        files = [("study", "SRP000539.json", "patch.json")]
        for schema, original_file, update_file in files:
            draft_id = await post_draft(client_logged_in, schema, submission_id, original_file)
            accession_id = await patch_draft(client_logged_in, schema, draft_id, update_file)
            async with client_logged_in.get(f"{drafts_url}/{schema}/{accession_id}") as resp:
                LOG.debug("Checking that %s JSON is in %s", accession_id, schema)
                res = await resp.json()
                assert res["centerName"] == "GEOM", "object centerName content mismatch"
                assert res["alias"] == "GSE10968", "object alias content mismatch"
                assert resp.status == 200, f"HTTP Status code error, got {resp.status}"
            await check_object_exists(client_logged_in, schema, accession_id, draft=True)

            await delete_draft(client_logged_in, schema, accession_id)
            async with client_logged_in.get(f"{drafts_url}/{schema}/{accession_id}") as resp:
                LOG.debug("Checking that JSON object %s was deleted", accession_id)
                assert resp.status == 404, f"HTTP Status code error, got {resp.status}"
