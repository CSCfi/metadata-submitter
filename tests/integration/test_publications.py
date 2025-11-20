"""Smoke test publications."""

import json
import logging
from typing import Any

from metadata_backend.api.json import to_json
from metadata_backend.api.models.models import Registration
from metadata_backend.api.models.submission import Rems
from tests.integration.conf import (
    auth,
    datacite_prefix,
    metax_api,
    mock_pid_prefix,
    submissions_url,
)
from tests.integration.helpers import (
    get_request_data,
    get_submission,
    get_submission_files,
    patch_submission_bucket,
    patch_submission_metadata,
    patch_submission_rems,
    publish_submission,
    submit_bp,
)

LOG = logging.getLogger(__name__)
LOG.setLevel(logging.DEBUG)


class TestMinimalPublication:
    """Test minimal publication with JSON submissions for FEGA and SDSX workflows, XML submissions for BP workflow."""

    async def test_sdsx_publication(self, client_logged_in, submission_factory, s3_manager, project_id):
        """Test SDSX publication.

        :param client_logged_in: HTTP client in which request call is made
        :param submission_factory: The factory that creates and deletes submissions
        """
        submission_id, _ = await submission_factory("SD")
        mock_bucket = "bucket1"
        file_name = "test_object"

        doi_data_raw = await get_request_data("submission", "metadata.json")
        await patch_submission_metadata(client_logged_in, submission_id, doi_data_raw)
        rems_data = await get_request_data("submission", "rems.json")
        await patch_submission_rems(client_logged_in, submission_id, rems_data)

        await s3_manager.add_bucket(mock_bucket)
        await s3_manager.set_bucket_policy(mock_bucket, project_id)
        await s3_manager.add_file_to_bucket(mock_bucket, file_name)
        await patch_submission_bucket(client_logged_in, submission_id, mock_bucket)

        await publish_submission(client_logged_in, submission_id, no_files=False)

        submission = await get_submission(client_logged_in, submission_id)
        LOG.debug("Checking that submission %s was published", submission_id)
        assert submission["submissionId"] == submission_id, "expected submission id does not match"
        assert submission["published"] is True, "submission is published, expected False"

        files = await get_submission_files(client_logged_in, submission_id)
        LOG.debug("Checking that submission %s has a file after publication", submission_id)
        assert len(files) == 1, "expected one file in the submission"
        assert files[0]["submissionId"] == submission_id, "expected submission id does not match"
        assert files[0]["path"] == f"S3://{mock_bucket}/{file_name}", "expected file path does not match"


class TestPublication:
    """Test publication to Metax and REMS."""

    async def test_sdsx_publication(self, client_logged_in, submission_factory):
        """Test SDSX publication.

        :param client_logged_in: HTTP client in which request call is made
        :param submission_factory: The factory that creates and deletes submissions
        """
        submission_id, _ = await submission_factory("SD")

        rems_data = await get_request_data("submission", "rems.json")
        await patch_submission_rems(client_logged_in, submission_id, rems_data)

        doi_data_raw = await get_request_data("submission", "metadata.json")
        await patch_submission_metadata(client_logged_in, submission_id, doi_data_raw)

        await publish_submission(client_logged_in, submission_id)

        async with client_logged_in.get(f"{submissions_url}/{submission_id}") as resp:
            LOG.debug(f"Checking that submission {submission_id} was published")
            res = await resp.json()
            assert res["submissionId"] == submission_id, "expected submission id does not match"
            assert res["published"] is True, "submission is published, expected False"

        async with client_logged_in.get(f"{submissions_url}/{submission_id}/registrations") as resp:
            assert resp.status == 200
            res = await resp.json()
            registration = Registration(**res[0])
            # Check DOI
            assert registration.doi.startswith(mock_pid_prefix)
            # Check that metax ID exists
            assert registration.metaxId is not None
            # Check REMS
            assert registration.remsResourceId is not None
            assert registration.remsCatalogueId is not None
            assert registration.remsUrl is not None

        # Check Metax mock service.
        async with client_logged_in.get(f"{metax_api}/{registration.metaxId}", auth=auth) as metax_resp:
            metax = await metax_resp.json()
            assert metax_resp.status == 200, f"HTTP Status code error, got {metax_resp.status}"
            await assert_metax(
                metax, registration.objectType, registration.title, registration.description, registration.doi
            )

    async def test_bigpicture_publication(self, client_logged_in, project_id):
        """Test BP publication.

        :param client_logged_in: HTTP client in which request call is made
        :param project_id: The project id.
        """
        submission = await submit_bp(client_logged_in, project_id)
        submission_id = submission.submissionId

        doi_data_raw = await get_request_data("submission", "metadata.json")
        await patch_submission_metadata(client_logged_in, submission_id, doi_data_raw)

        # Change REMS information extracted from BP REMS XML and stored in submission.json.
        await patch_submission_rems(
            client_logged_in, submission_id, to_json(Rems(workflowId=1, organizationId="CSC", licenses=[1]))
        )

        await publish_submission(client_logged_in, submission_id)

        async with client_logged_in.get(f"{submissions_url}/{submission_id}") as resp:
            LOG.debug(f"Checking that submission {submission_id} was published")
            res = await resp.json()
            assert res["submissionId"] == submission_id, "expected submission id does not match"
            assert res["published"] is True, "submission is published, expected False"

        async with client_logged_in.get(f"{submissions_url}/{submission_id}/registrations") as resp:
            assert resp.status == 200
            res = await resp.json()
            registration = Registration(**res[0])
            # Check DOI
            assert registration.doi.startswith(
                datacite_prefix
            ), "expected BP dataset DOI to be created directly with Datacite"
            # Check that metax ID does not exist
            assert registration.metaxId is None
            # Check REMS
            assert registration.remsResourceId is not None
            assert registration.remsCatalogueId is not None
            assert registration.remsUrl is not None


async def assert_metax(metax: dict[str, Any], schema: str, title: str, description: str, doi: str):
    expected_rd = json.loads(await get_request_data("metax", "research_dataset.json"))
    actual_rd = metax["research_dataset"]

    # title = res["title"] if schema == "dataset" else res["descriptor"]["studyTitle"]
    # description = res["description"] if schema == "dataset" else res["descriptor"]["studyAbstract"]

    assert actual_rd["preferred_identifier"] == doi
    assert actual_rd["title"]["en"] == title
    assert actual_rd["description"]["en"].split("\n\n")[0] == description
    assert actual_rd["creator"] == expected_rd["creator"]
    assert (
        actual_rd["access_rights"]["access_type"]["identifier"]
        == expected_rd["access_rights"]["access_type"]["identifier"]
    )
    assert actual_rd["contributor"] == expected_rd["contributor"]
    assert actual_rd["issued"] == expected_rd["issued"]
    assert actual_rd["modified"] == expected_rd["modified"]
    assert actual_rd["other_identifier"][0]["notation"] == expected_rd["other_identifier"][0]["notation"]
    assert actual_rd["publisher"] == expected_rd["publisher"]
    assert actual_rd["spatial"] == expected_rd["spatial"]
    assert actual_rd["temporal"] == expected_rd["temporal"]
    assert actual_rd["language"] == expected_rd["language"]
    assert actual_rd["field_of_science"] == expected_rd["field_of_science"]

    if schema == "study":
        assert "relation" in actual_rd
    if schema == "dataset":
        assert "is_output_of" in actual_rd
