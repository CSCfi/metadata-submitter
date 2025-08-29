"""Test operations with submissions."""

import json
import logging

from metadata_backend.api.models import Object
from tests.integration.conf import objects_url, publish_url
from tests.integration.helpers import (
    add_submission_linked_folder,
    delete_object,
    delete_submission,
    get_object,
    get_request_data,
    get_submission,
    patch_submission_doi,
    patch_submission_rems,
    post_object,
    post_object_data,
    publish_submission,
    submissions_url,
)

LOG = logging.getLogger(__name__)
LOG.setLevel(logging.DEBUG)


class TestSubmissions:
    """Test querying submissions and their objects."""

    async def test_get_submissions(self, client_logged_in, submission_factory, project_id):
        """Test submissions REST API GET .

        :param client_logged_in: HTTP client in which request call is made
        :param submission_factory: The factory that creates and deletes submissions
        :param project_id: id of the project the submission belongs to
        """
        submission_id, _ = await submission_factory("FEGA")

        page_size = 1000

        async with client_logged_in.get(f"{submissions_url}?projectId={project_id}&per_page={page_size}") as resp:
            LOG.debug("Reading submission %s", submission_id)
            assert resp.status == 200, f"HTTP Status code error, got {resp.status}"
            response = await resp.json()
            assert response["page"] == {
                "page": 1,
                "size": page_size,
                "totalPages": 1,
                "totalSubmissions": len(response["submissions"]),
            }
            assert submission_id in [r["submissionId"] for r in response["submissions"]]

    async def test_get_submissions_objects(self, client_logged_in, submission_factory):
        """Test submissions REST API GET with objects.

        :param client_logged_in: HTTP client in which request call is made
        :param submission_factory: The factory that creates and deletes submissions
        """
        submission_id, _ = await submission_factory("FEGA")

        schema = "study"
        accession_id = await post_object(client_logged_in, schema, submission_id, "SRP000539.json")
        async with client_logged_in.get(f"{objects_url}/{schema}?submission={submission_id}") as resp:
            LOG.debug("Reading submission %s", submission_id)
            assert resp.status == 200, f"HTTP Status code error, got {resp.status}"
            response = await resp.json()
            assert accession_id in [Object(**r).object_id for r in response]

        await delete_object(client_logged_in, "study", accession_id)


class TestSubmissionOperations:
    """Testing basic CRUD submission operations."""

    async def test_crud_submissions_works(self, client_logged_in, submission_factory, project_id):
        """Test submissions REST api POST, GET, PATCH, PUBLISH and DELETE reqs.

        :param client_logged_in: HTTP client in which request call is made
        :param submission_factory: The factory that creates and deletes submissions
        :param project_id: id of the project the submission belongs to
        """
        submission_id, submission_data = await submission_factory("FEGA")

        async with client_logged_in.get(f"{submissions_url}/{submission_id}") as resp:
            LOG.debug("Checking that submission %s was created", submission_id)
            assert resp.status == 200, f"HTTP Status code error, got {resp.status}"

        # Try creating the same submission again and check that it fails
        async with client_logged_in.post(f"{submissions_url}", data=json.dumps(submission_data)) as resp:
            ans = await resp.json()
            assert resp.status == 400, f"HTTP Status code error {resp.status} {ans}"
            assert (
                ans["detail"]
                == f"Submission with name '{submission_data["name"]}' already exists in project {project_id}"
            )

        # Add XML object
        accession_id = await post_object(client_logged_in, "sample", submission_id, "SRS001433.xml")
        async with client_logged_in.get(f"{submissions_url}/{submission_id}") as resp:
            LOG.debug("Checking that submission %s was patched", submission_id)
            res = await resp.json()
            assert res["submissionId"] == submission_id, "expected submission id does not match"
            assert res["name"] == submission_data["name"], "expected submission name does not match"
            assert res["description"] == submission_data["description"], "submission description content mismatch"
            assert res["published"] is False, "submission is published, expected False"

        async with client_logged_in.get(f"{submissions_url}/{submission_id}") as resp:
            LOG.debug("Checking that submission %s was patched", submission_id)
            res = await resp.json()
            assert res["submissionId"] == submission_id, "expected submission id does not match"
            assert res["published"] is False, "submission is published, expected False"
            assert "datePublished" not in res.keys()

        # Add DOI for publishing the submission
        doi_data_raw = await get_request_data("doi", "test_doi.json")
        await patch_submission_doi(client_logged_in, submission_id, doi_data_raw)

        # Add a study and dataset for publishing a submission
        dataset = await post_object(client_logged_in, "dataset", submission_id, "dataset.xml")
        study = await post_object(client_logged_in, "study", submission_id, "SRP000539.json")
        dac = await post_object(client_logged_in, "dac", submission_id, "dac.xml")

        rems_data = await get_request_data("dac", "dac_rems.json")
        await patch_submission_rems(client_logged_in, submission_id, rems_data)
        await post_object(client_logged_in, "policy", submission_id, "policy.json")
        await post_object(client_logged_in, "run", submission_id, "ERR000076.json")

        submission_id = await publish_submission(client_logged_in, submission_id)
        await get_object(client_logged_in, "dataset", dataset)
        await get_object(client_logged_in, "study", study)
        await get_object(client_logged_in, "dac", dac)

        async with client_logged_in.get(f"{submissions_url}/{submission_id}") as resp:
            LOG.debug("Checking that submission %s was patched", submission_id)
            res = await resp.json()
            assert res["submissionId"] == submission_id, "expected submission id does not match"
            assert res["published"] is True
            assert "datePublished" in res.keys()
            assert "rems" in res.keys(), "submission does not have rems dac data"

        # Check that submission info and its objects cannot be updated and that publishing it again fails
        async with client_logged_in.patch(
            f"{submissions_url}/{submission_id}", data=json.dumps({"name": "new_name"})
        ) as resp:
            LOG.debug("Trying to update submission values")
            assert resp.status == 400, f"HTTP Status code error, got {resp.status}"
        async with client_logged_in.patch(
            f"{objects_url}/sample/{accession_id}", params={"submission": submission_id}, json={}
        ) as resp:
            LOG.debug("Trying to update submission objects")
            assert resp.status == 400, f"HTTP Status code error, got {resp.status}"
        async with client_logged_in.patch(f"{publish_url}/{submission_id}") as resp:
            LOG.debug("Trying to re-publish submission %s", submission_id)
            assert resp.status == 400, f"HTTP Status code error, got {resp.status}"

        # Check submission objects cannot be replaced
        sample = await get_request_data("sample", "SRS001433.xml")
        async with client_logged_in.put(
            f"{objects_url}/sample/{accession_id}", params={"submission": submission_id}, data=sample
        ) as resp:
            LOG.debug("Trying to replace submission objects")
            assert resp.status == 400, f"HTTP Status code error, got {resp.status}"
        async with client_logged_in.patch(f"{submissions_url}/{submission_id}/doi", data=doi_data_raw) as resp:
            LOG.debug("Trying to replace submission doi")
            assert resp.status == 400, f"HTTP Status code error {resp.status} {ans}"
        async with client_logged_in.patch(f"{submissions_url}/{submission_id}/rems", data=rems_data) as resp:
            LOG.debug("Trying to replace submission rems")
            assert resp.status == 400, f"HTTP Status code error {resp.status} {ans}"

        # Check that objects cannot be added under published submission
        run = await get_request_data("run", "ERR000076.json")
        async with client_logged_in.post(f"{objects_url}/run", params={"submission": submission_id}, data=run) as resp:
            LOG.debug("Trying to add object to already published submission")
            assert resp.status == 400, f"HTTP Status code error, got {resp.status}"

        # Attempt deleting submission
        async with client_logged_in.delete(f"{submissions_url}/{submission_id}") as resp:
            assert resp.status == 400, f"HTTP Status code error, got {resp.status}"

    async def test_crud_submissions_works_no_publish(self, client_logged_in, submission_factory):
        """Test submissions REST API POST, GET, PATCH, PUBLISH and DELETE reqs.

        :param client_logged_in: HTTP client in which request call is made
        :param submission_factory: The factory that creates and deletes submissions
        """
        submission_id, submission_data = await submission_factory("FEGA")

        async with client_logged_in.get(f"{submissions_url}/{submission_id}") as resp:
            LOG.debug("Checking that submission %s was created", submission_id)
            assert resp.status == 200, f"HTTP Status code error, got {resp.status}"

        # Add XML object.
        object_id = await post_object(client_logged_in, "sample", submission_id, "SRS001433.xml")
        async with client_logged_in.get(f"{submissions_url}/{submission_id}") as resp:
            LOG.debug("Checking that submission %s was patched", submission_id)
            res = await resp.json()
            assert res["submissionId"] == submission_id, "expected submission id does not match"
            assert res["name"] == submission_data["name"], "expected submission name does not match"
            assert res["description"] == submission_data["description"], "submission description content mismatch"
            assert res["published"] is False, "submission is published, expected False"

        async with client_logged_in.get(f"{submissions_url}/{submission_id}") as resp:
            LOG.debug("Checking that submission %s was patched", submission_id)
            res = await resp.json()
            assert res["submissionId"] == submission_id, "expected submission id does not match"
            assert res["published"] is False, "submission is published, expected False"

        # Delete submission
        await delete_submission(client_logged_in, submission_id)
        async with client_logged_in.get(f"{submissions_url}/{submission_id}") as resp:
            LOG.debug("Checking that submission %s was deleted", submission_id)
            assert resp.status == 404, f"HTTP Status code error, got {resp.status}"

    async def test_adding_doi_info_to_submission_works(self, client_logged_in, submission_factory):
        """Test that proper DOI info can be added to submission and bad DOI info cannot be.

        :param client_logged_in: HTTP client in which request call is made
        :param submission_factory: The factory that creates and deletes submissions
        """
        submission_id, submission_data = await submission_factory("FEGA")

        async with client_logged_in.get(f"{submissions_url}/{submission_id}") as resp:
            LOG.debug("Checking that submission %s was created", submission_id)
            assert resp.status == 200, f"HTTP Status code error, got {resp.status}"

        # Get correctly formatted DOI info and patch it into the new submission successfully
        doi_data_raw = await get_request_data("doi", "test_doi.json")
        doi_data = json.loads(doi_data_raw)
        await patch_submission_doi(client_logged_in, submission_id, doi_data_raw)

        async with client_logged_in.get(f"{submissions_url}/{submission_id}") as resp:
            LOG.debug("Checking that submission %s was patched", submission_id)
            res = await resp.json()
            assert res["submissionId"] == submission_id, "expected submission id does not match"
            assert res["name"] == submission_data["name"], "expected submission name does not match"
            assert res["description"] == submission_data["description"], "submission description content mismatch"
            assert res["published"] is False, "submission is published, expected False"
            assert res["doiInfo"] == doi_data, "submission doi does not match"

        # Test that an incomplete DOI object fails to patch into the submission
        put_bad_doi = {"identifier": {}}
        async with client_logged_in.patch(
            f"{submissions_url}/{submission_id}/doi", data=json.dumps(put_bad_doi)
        ) as resp:
            LOG.debug("Tried updating submission %s", submission_id)
            assert resp.status == 400, f"HTTP Status code error, got {resp.status}"
            res = await resp.json()
            assert (
                res["detail"] == "Provided input does not seem correct for field: 'doiInfo'"
            ), "expected error mismatch"

        # Check the existing DOI info is not altered
        async with client_logged_in.get(f"{submissions_url}/{submission_id}") as resp:
            LOG.debug("Checking that submission %s was not patched with bad DOI", submission_id)
            res = await resp.json()
            assert res["doiInfo"] == doi_data, "submission doi does not match"

        # Delete submission
        await delete_submission(client_logged_in, submission_id)
        async with client_logged_in.get(f"{submissions_url}/{submission_id}") as resp:
            LOG.debug("Checking that submission %s was deleted", submission_id)
            assert resp.status == 404, f"HTTP Status code error, got {resp.status}"

    async def test_linking_folder_to_submission_works(self, client_logged_in, submission_factory):
        """Test that a folder name can be linked to a submission.

        :param client_logged_in: HTTP client in which request call is made
        :param submission_factory: The factory that creates and deletes submissions
        """
        submission_id, _ = await submission_factory("SDSX")

        async with client_logged_in.get(f"{submissions_url}/{submission_id}") as resp:
            LOG.debug("Checking that submission %s was created", submission_id)
            assert resp.status == 200, f"HTTP Status code error, got {resp.status}"

        submission = await get_submission(client_logged_in, submission_id)
        assert "linkedFolder" not in submission

        folder = "test"
        await add_submission_linked_folder(client_logged_in, submission_id, folder)
        submission = await get_submission(client_logged_in, submission_id)
        assert submission["linkedFolder"] == folder

    async def test_adding_rems_info_to_submission_works(self, client_logged_in, submission_factory):
        """Test that correct REMS info can be added to submission and invalid REMS info will raise error.

        :param client_logged_in: HTTP client in which request call is made
        :param submission_factory: The factory that creates and deletes submissions
        """
        submission_id, submission_data = await submission_factory("SDSX")

        async with client_logged_in.get(f"{submissions_url}/{submission_id}") as resp:
            LOG.debug("Checking that submission %s was created", submission_id)
            assert resp.status == 200, f"HTTP Status code error, got {resp.status}"

        # Get correctly formatted REMS info and patch it into the new submission successfully
        rems_data_raw = await get_request_data("dac", "dac_rems.json")
        rems_data = json.loads(rems_data_raw)
        await patch_submission_rems(client_logged_in, submission_id, rems_data_raw)

        async with client_logged_in.get(f"{submissions_url}/{submission_id}") as resp:
            LOG.debug("Checking that submission %s was patched", submission_id)
            res = await resp.json()
            assert res["submissionId"] == submission_id, "expected submission id does not match"
            assert res["name"] == submission_data["name"], "expected submission name does not match"
            assert res["description"] == submission_data["description"], "submission description content mismatch"
            assert res["published"] is False, "submission is published, expected False"
            assert res["rems"] == rems_data, "rems info does not match"

        # Test that an incorrect REMS object fails to patch into the submission
        # error case: REMS's licenses do not include DAC's linked license
        put_bad_rems = {"workflowId": 1, "organizationId": "CSC", "licenses": [2, 3]}
        async with client_logged_in.patch(
            f"{submissions_url}/{submission_id}/rems", data=json.dumps(put_bad_rems)
        ) as resp:
            LOG.debug("Tried updating submission %s", submission_id)
            assert resp.status == 400, f"HTTP Status code error, got {resp.status}"
            res = await resp.json()
            assert (
                res["detail"] == "Rems error: Linked license '1' doesn't exist in licenses '[2, 3]'"
            ), "expected error mismatch"
