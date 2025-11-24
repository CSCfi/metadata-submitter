"""Test operations with submissions."""

import json
import logging

from tests.integration.conf import publish_url
from tests.integration.helpers import (
    delete_submission,
    get_request_data,
    get_submission,
    patch_submission_bucket,
    patch_submission_metadata,
    patch_submission_rems,
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


class TestSubmissionOperations:
    """Testing basic CRUD submission operations."""

    async def test_sdsx_submission(self, client_logged_in, submission_factory, project_id):
        """Test submissions REST api POST, GET, PATCH, PUBLISH and DELETE reqs.

        :param client_logged_in: HTTP client in which request call is made
        :param submission_factory: The factory that creates and deletes submissions
        :param project_id: id of the project the submission belongs to
        """
        submission_id, submission_data = await submission_factory("SD")

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

        # Test get submission
        async with client_logged_in.get(f"{submissions_url}/{submission_id}") as resp:
            res = await resp.json()
            assert res["submissionId"] == submission_id, "expected submission id does not match"
            assert res["name"] == submission_data["name"], "expected submission name does not match"
            assert res["description"] == submission_data["description"], "submission description content mismatch"
            assert res["published"] is False, "submission is published, expected False"

        # Add metadata for publishing the submission
        metadata_raw = await get_request_data("submission", "metadata.json")
        await patch_submission_metadata(client_logged_in, submission_id, metadata_raw)

        # Add REMS for publishing the submission
        rems_data = await get_request_data("submission", "rems.json")
        await patch_submission_rems(client_logged_in, submission_id, rems_data)

        # Publish submission
        submission_id = await publish_submission(client_logged_in, submission_id)

        # Check published date
        async with client_logged_in.get(f"{submissions_url}/{submission_id}") as resp:
            LOG.debug("Checking that submission %s was patched", submission_id)
            res = await resp.json()
            assert res["submissionId"] == submission_id, "expected submission id does not match"
            assert res["published"] is True
            assert "datePublished" in res.keys()
            assert "rems" in res.keys(), "submission does not have rems dac data"

        # Check that published submission can't be changed.
        async with client_logged_in.patch(
            f"{submissions_url}/{submission_id}", data=json.dumps({"name": "new_name"})
        ) as resp:
            LOG.debug("Trying to update submission values")
            assert resp.status == 400, f"HTTP Status code error, got {resp.status}"

        # Check that published submission can't be re-published.
        async with client_logged_in.patch(f"{publish_url}/{submission_id}") as resp:
            LOG.debug("Trying to re-publish submission %s", submission_id)
            assert resp.status == 400, f"HTTP Status code error, got {resp.status}"

        # Check that published submission can't be deleted.
        async with client_logged_in.delete(f"{submissions_url}/{submission_id}") as resp:
            assert resp.status == 400, f"HTTP Status code error, got {resp.status}"

    async def test_sdsx_metadata(self, client_logged_in, submission_factory):
        """Test adding metadata to submission.

        :param client_logged_in: HTTP client in which request call is made
        :param submission_factory: The factory that creates and deletes submissions
        """
        submission_id, submission_data = await submission_factory("SD")

        async with client_logged_in.get(f"{submissions_url}/{submission_id}") as resp:
            LOG.debug("Checking that submission %s was created", submission_id)
            assert resp.status == 200, f"HTTP Status code error, got {resp.status}"

        # Get correctly formatted metadata and patch it into the new submission successfully
        submission_metadata_str = await get_request_data("submission", "metadata.json")
        await patch_submission_metadata(client_logged_in, submission_id, submission_metadata_str)

        expected_submission_metadata_str = await get_request_data("submission", "saved_metadata.json")
        expected_submission_metadata = json.loads(expected_submission_metadata_str)

        async with client_logged_in.get(f"{submissions_url}/{submission_id}") as resp:
            LOG.debug("Checking that submission %s was patched", submission_id)
            res = await resp.json()
            assert res["submissionId"] == submission_id, "expected submission id does not match"
            assert res["name"] == submission_data["name"], "expected submission name does not match"
            assert res["description"] == submission_data["description"], "submission description content mismatch"
            assert res["published"] is False, "submission is published, expected False"
            assert res["metadata"] == expected_submission_metadata, "submission doi does not match"

        # Test that an incomplete DOI object fails to patch into the submission
        bad_metadata = {"invalid": {}}
        async with client_logged_in.patch(
            f"{submissions_url}/{submission_id}", json={"metadata": bad_metadata}
        ) as resp:
            LOG.debug("Tried updating submission %s", submission_id)
            assert resp.status == 400, f"HTTP Status code error, got {resp.status}"
            res = await resp.json()
            assert (
                res["detail"] == "metadata.creators: Field required; metadata.invalid: Extra inputs are not permitted"
            )

        # Check the existing DOI info is not altered
        async with client_logged_in.get(f"{submissions_url}/{submission_id}") as resp:
            LOG.debug("Checking that submission %s was not patched with bad DOI", submission_id)
            res = await resp.json()
            assert res["metadata"] == expected_submission_metadata, "submission doi does not match"

        # Delete submission
        await delete_submission(client_logged_in, submission_id)
        async with client_logged_in.get(f"{submissions_url}/{submission_id}") as resp:
            LOG.debug("Checking that submission %s was deleted", submission_id)
            assert resp.status == 404, f"HTTP Status code error, got {resp.status}"

    async def test_sdsx_bucket(self, client_logged_in, submission_factory):
        """Test that a bucket name can be linked to a submission.

        :param client_logged_in: HTTP client in which request call is made
        :param submission_factory: The factory that creates and deletes submissions
        """
        submission_id, _ = await submission_factory("SD")

        async with client_logged_in.get(f"{submissions_url}/{submission_id}") as resp:
            LOG.debug("Checking that submission %s was created", submission_id)
            assert resp.status == 200, f"HTTP Status code error, got {resp.status}"

        submission = await get_submission(client_logged_in, submission_id)
        assert "bucket" not in submission

        bucket = "test"
        await patch_submission_bucket(client_logged_in, submission_id, bucket)
        submission = await get_submission(client_logged_in, submission_id)
        assert submission["bucket"] == bucket

    async def test_sdsx_rems(self, client_logged_in, submission_factory):
        """Test that correct REMS info can be added to submission and invalid REMS info will raise error.

        :param client_logged_in: HTTP client in which request call is made
        :param submission_factory: The factory that creates and deletes submissions
        """
        submission_id, submission_data = await submission_factory("SD")

        async with client_logged_in.get(f"{submissions_url}/{submission_id}") as resp:
            LOG.debug("Checking that submission %s was created", submission_id)
            assert resp.status == 200, f"HTTP Status code error, got {resp.status}"

        # Get correctly formatted REMS info and patch it into the new submission successfully
        rems_data_raw = await get_request_data("submission", "rems.json")
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
        bad_rems = {"invalid": {}}
        async with client_logged_in.patch(f"{submissions_url}/{submission_id}", json={"rems": bad_rems}) as resp:
            LOG.debug("Tried updating submission %s", submission_id)
            assert resp.status == 400, f"HTTP Status code error, got {resp.status}"
            res = await resp.json()
            assert (
                res["detail"]
                == "rems.workflowId: Field required; rems.organizationId: Field required; rems.licenses: Field required; rems.invalid: Extra inputs are not permitted"
            ), "expected error mismatch"
