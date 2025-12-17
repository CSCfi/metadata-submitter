"""Smoke test publications."""

import json
import logging

from tests.integration.conf import (
    submissions_url,
)
from tests.integration.helpers import (
    get_request_data,
    get_submission,
    get_submission_files,
    patch_submission_bucket,
    publish_submission,
    submit_bp,
)

LOG = logging.getLogger(__name__)
LOG.setLevel(logging.DEBUG)


async def test_sd_publication(client_logged_in, submission_factory, s3_manager, project_id):
    """Test  SD submission from beginning to publication."""

    submission = json.loads(await get_request_data("submission", "submission.json"))

    submission_id, _ = await submission_factory(workflow="SD", submission=submission)
    mock_bucket = "bucket1"
    file_name = "test_object"

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


# TODO(improve): consider reintroducing commented out test after individual publish integreation tests work.

# async def test_metax_rems_publication(client_logged_in, submission_factory):
#     """Test publication to Metax and REMS.
#
#     :param client_logged_in: HTTP client in which request call is made
#     :param submission_factory: The factory that creates and deletes submissions
#     """
#     submission_id, _ = await submission_factory("SD")
#
#     rems_data = await get_request_data("submission", "rems.json")
#     await patch_submission_rems(client_logged_in, submission_id, rems_data)
#
#     doi_data_raw = await get_request_data("submission", "metadata.json")
#     await patch_submission_metadata(client_logged_in, submission_id, doi_data_raw)
#
#     await publish_submission(client_logged_in, submission_id)
#
#     async with client_logged_in.get(f"{submissions_url}/{submission_id}") as resp:
#         LOG.debug(f"Checking that submission {submission_id} was published")
#         res = await resp.json()
#         assert res["submissionId"] == submission_id, "expected submission id does not match"
#         assert res["published"] is True, "submission is published, expected False"
#
#     async with client_logged_in.get(f"{submissions_url}/{submission_id}/registrations") as resp:
#         assert resp.status == 200
#         res = await resp.json()
#         registration = Registration(**res[0])
#         # Check DOI
#         assert registration.doi.startswith(mock_pid_prefix)
#         # Check that metax ID exists
#         assert registration.metaxId is not None
#         # Check REMS
#         assert registration.remsResourceId is not None
#         assert registration.remsCatalogueId is not None
#         assert registration.remsUrl is not None
#
#     # Check Metax mock service.
#     async with client_logged_in.get(f"{metax_api}/{registration.metaxId}", auth=auth) as metax_resp:
#         metax = await metax_resp.json()
#         assert metax_resp.status == 200, f"HTTP Status code error, got {metax_resp.status}"
#         await assert_metax(
#             metax, registration.objectType, registration.title, registration.description, registration.doi
#         )


async def test_bigpicture_publication(client_logged_in, project_id):
    """Test Bigpicture submission from beginning to publication."""

    submission = await submit_bp(client_logged_in, project_id)
    submission_id = submission.submissionId

    await publish_submission(client_logged_in, submission_id)

    async with client_logged_in.get(f"{submissions_url}/{submission_id}") as resp:
        LOG.debug(f"Checking that submission {submission_id} was published")
        res = await resp.json()
        assert res["submissionId"] == submission_id, "expected submission id does not match"
        assert res["published"] is True, "submission is published, expected False"

    # TODO(improve): consider reintroducing commented out test after individual publish integreation tests work.

    # async with client_logged_in.get(f"{submissions_url}/{submission_id}/registrations") as resp:
    #     assert resp.status == 200
    #     res = await resp.json()
    #     registration = Registration(**res[0])
    #     # Check DOI
    #     assert registration.doi.startswith("10.xxxx")
    #     # Check that metax ID does not exist
    #     assert registration.metaxId is None
    #     # Check REMS
    #     assert registration.remsResourceId is not None
    #     assert registration.remsCatalogueId is not None
    #     assert registration.remsUrl is not None
