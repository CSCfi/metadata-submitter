"""Test operations with draft objects."""
import asyncio
import logging

from tests.integration.conf import drafts_url, submissions_url, test_json_files
from tests.integration.helpers import (
    check_submissions_object_patch,
    delete_draft,
    patch_draft,
    post_draft_json,
    put_draft,
)

LOG = logging.getLogger(__name__)
LOG.setLevel(logging.DEBUG)


class TestDrafts:
    """Test operations with draft."""

    async def test_crud_drafts_works(self, client_logged_in, submission_fega):
        """Test drafts REST API POST, PUT and DELETE reqs.

        Tries to create new draft object, gets accession id and checks if correct
        resource is returned with that id. Finally deletes the object and checks it
        was deleted.

        :param client_logged_in: HTTP client in which request call is made
        :param submission_fega: id of the submission used to group submission objects
        """

        async def crud_drafts_works(schema, original_file, update_file):
            """Individual tests to be run in parallel."""
            draft_id = await post_draft_json(client_logged_in, schema, submission_fega, original_file)
            async with client_logged_in.get(f"{drafts_url}/{schema}/{draft_id}") as resp:
                assert resp.status == 200, f"HTTP Status code error, got {resp.status}"
                res = await resp.json()
                title = res["descriptor"]["studyTitle"] if schema == "study" else res.get("title", "")
            await check_submissions_object_patch(
                client_logged_in,
                submission_fega,
                draft_id,
                schema,
                title,
                original_file,
                draft=True,
            )

            accession_id = await put_draft(client_logged_in, schema, draft_id, update_file)
            async with client_logged_in.get(f"{drafts_url}/{schema}/{accession_id}") as resp:
                LOG.debug(f"Checking that {accession_id} JSON is in {schema}")
                assert resp.status == 200, f"HTTP Status code error, got {resp.status}"
                res = await resp.json()
                title = res["descriptor"]["studyTitle"] if schema == "study" else res.get("title", "")
            await check_submissions_object_patch(
                client_logged_in,
                submission_fega,
                schema,
                accession_id,
                title,
                update_file,
                draft=True,
            )

            await delete_draft(client_logged_in, schema, accession_id)
            async with client_logged_in.get(f"{drafts_url}/{schema}/{accession_id}") as resp:
                LOG.debug(f"Checking that JSON object {accession_id} was deleted")
                assert resp.status == 404, f"HTTP Status code error, got {resp.status}"

            async with client_logged_in.get(f"{submissions_url}/{submission_fega}") as resp:
                LOG.debug(f"Checking that JSON object {accession_id} was deleted from submission {submission_fega}")
                res = await resp.json()
                expected_true = not any(d["accessionId"] == accession_id for d in res["drafts"])
                assert expected_true, f"draft object {accession_id} still exists"

        gather_items = []
        # Run in parallel to test concurrent uploads
        files = test_json_files + [("sample", "SRS001433.json", "put.json")]
        for schema, original_file, update_file in files:
            gather_items.append(crud_drafts_works(schema, original_file, update_file))
        await asyncio.gather(*gather_items)

    async def test_patch_drafts_works(self, client_logged_in, submission_fega):
        """Test REST API POST, PATCH and DELETE reqs.

        Tries to create put and patch object, gets accession id and
        checks if correct resource is returned with that id.
        Finally deletes the object and checks it was deleted.

        :param client_logged_in: HTTP client in which request call is made
        :param submission_fega: id of the submission used to group submission objects
        """
        files = [("study", "SRP000539.json", "patch.json")]
        for schema, original_file, update_file in files:
            draft_id = await post_draft_json(client_logged_in, schema, submission_fega, original_file)
            accession_id = await patch_draft(client_logged_in, schema, draft_id, update_file)
            async with client_logged_in.get(f"{drafts_url}/{schema}/{accession_id}") as resp:
                LOG.debug(f"Checking that {accession_id} JSON is in {schema}")
                res = await resp.json()
                title = res["descriptor"]["studyTitle"] if schema == "study" else res.get("title", None)
                assert res["centerName"] == "GEOM", "object centerName content mismatch"
                assert res["alias"] == "GSE10968", "object alias content mismatch"
                assert resp.status == 200, f"HTTP Status code error, got {resp.status}"
            await check_submissions_object_patch(
                client_logged_in,
                submission_fega,
                schema,
                accession_id,
                title,
                update_file,
                draft=True,
            )

            await delete_draft(client_logged_in, schema, accession_id)
            async with client_logged_in.get(f"{drafts_url}/{schema}/{accession_id}") as resp:
                LOG.debug(f"Checking that JSON object {accession_id} was deleted")
                assert resp.status == 404, f"HTTP Status code error, got {resp.status}"
