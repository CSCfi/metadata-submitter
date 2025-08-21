"""Smoke test publications."""

import logging

from metadata_backend.api.models import Registration
from tests.integration.conf import (
    datacite_prefix,
    mock_pid_prefix,
    submissions_url,
)
from tests.integration.helpers import (
    add_submission_linked_folder,
    get_request_data,
    get_submission,
    get_submission_files,
    patch_submission_doi,
    patch_submission_rems,
    post_object,
    publish_submission,
)

LOG = logging.getLogger(__name__)
LOG.setLevel(logging.DEBUG)


class TestMinimalPublication:
    """Test minimal publication with JSON submissions for FEGA and SDSX workflows, XML submissions for BP workflow."""

    async def test_sdsx_publication(self, client_logged_in, submission_factory, s3_manager):
        """Test SDSX publication.

        :param client_logged_in: HTTP client in which request call is made
        :param submission_factory: The factory that creates and deletes submissions
        """
        submission_id, _ = await submission_factory("SDSX")
        mock_folder = "folder1"
        file_name = "test_object"

        doi_data_raw = await get_request_data("doi", "test_doi.json")
        await patch_submission_doi(client_logged_in, submission_id, doi_data_raw)
        rems_data = await get_request_data("dac", "dac_rems.json")
        await patch_submission_rems(client_logged_in, submission_id, rems_data)

        await s3_manager.add_folder(mock_folder)
        await s3_manager.add_file_to_folder(mock_folder, file_name)
        await add_submission_linked_folder(client_logged_in, submission_id, mock_folder)

        await publish_submission(client_logged_in, submission_id, no_files=False)

        submission = await get_submission(client_logged_in, submission_id)
        LOG.debug("Checking that submission %s was published", submission_id)
        assert submission["submissionId"] == submission_id, "expected submission id does not match"
        assert submission["published"] is True, "submission is published, expected False"

        files = await get_submission_files(client_logged_in, submission_id)
        LOG.debug("Checking that submission %s has a file after publication", submission_id)
        assert len(files) == 1, "expected one file in the submission"
        assert files[0]["submissionId"] == submission_id, "expected submission id does not match"
        assert files[0]["path"] == f"S3://{mock_folder}/{file_name}", "expected file path does not match"


class TestPublication:
    """Test publication to Metax and REMS."""

    async def test_fega_json_publication_rems(self, client_logged_in, submission_factory):
        """Test FEGA publication workflow with JSON submissions to Metax and REMS.

        :param client_logged_in: HTTP client in which request call is made
        :param submission_factory: The factory that creates and deletes submissions
        """
        submission_id, _ = await submission_factory("FEGA")

        objects = []
        study_id = await post_object(client_logged_in, "study", submission_id, "SRP000539.json")
        objects.append(["study", study_id])

        await post_object(client_logged_in, "dac", submission_id, "dac.json")
        await post_object(client_logged_in, "policy", submission_id, "policy.json")
        await post_object(client_logged_in, "sample", submission_id, "SRS001433.json")
        await post_object(client_logged_in, "experiment", submission_id, "ERX000119.json")
        await post_object(client_logged_in, "analysis", submission_id, "ERZ266973.json")
        await post_object(client_logged_in, "run", submission_id, "ERR000076.json")

        dataset_id = await post_object(client_logged_in, "dataset", submission_id, "dataset.json")
        objects.append(["dataset", dataset_id])

        doi_data_raw = await get_request_data("doi", "test_doi.json")
        await patch_submission_doi(client_logged_in, submission_id, doi_data_raw)

        rems_data = await get_request_data("dac", "dac_rems.json")
        await patch_submission_rems(client_logged_in, submission_id, rems_data)

        await publish_submission(client_logged_in, submission_id)

        async with client_logged_in.get(f"{submissions_url}/{submission_id}") as resp:
            LOG.debug(f"Checking that submission {submission_id} was published")
            res = await resp.json()
            assert res["submissionId"] == submission_id, "expected submission id does not match"
            assert res["published"] is True, "submission is published, expected False"

        async with client_logged_in.get(f"{submissions_url}/{submission_id}/registrations") as resp:
            assert resp.status == 200
            res = await resp.json()
            study_registration = Registration(**[r for r in res if r["schema"] == "study"][0])
            dataset_registration = Registration(**[r for r in res if r["schema"] == "dataset"][0])
            # Check DOI
            assert study_registration.doi.startswith(mock_pid_prefix)
            assert dataset_registration.doi.startswith(mock_pid_prefix)
            # Check that metax ID exists
            assert study_registration.metax_id is not None
            assert dataset_registration.metax_id is not None
            # Check REMS
            assert study_registration.rems_resource_id is None
            assert study_registration.rems_catalogue_id is None
            assert study_registration.rems_url is None
            assert dataset_registration.rems_resource_id is not None
            assert dataset_registration.rems_catalogue_id is not None
            assert dataset_registration.rems_url is not None

    async def test_sdsx_publication_rems(self, client_logged_in, submission_factory):
        """Test SDSX publication to Metax and REMS.

        :param client_logged_in: HTTP client in which request call is made
        :param submission_factory: The factory that creates and deletes submissions
        """
        submission_id, _ = await submission_factory("SDSX")

        rems_data = await get_request_data("dac", "dac_rems.json")
        await patch_submission_rems(client_logged_in, submission_id, rems_data)

        doi_data_raw = await get_request_data("doi", "test_doi.json")
        await patch_submission_doi(client_logged_in, submission_id, doi_data_raw)

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
            assert registration.metax_id is not None
            # Check REMS
            assert registration.rems_resource_id is not None
            assert registration.rems_catalogue_id is not None
            assert registration.rems_url is not None

    async def test_full_bigpicture_xml_publication_rems(self, client_logged_in, submission_factory):
        """Test BP publication workflow with XML submissions to Metax and REMS.

        :param client_logged_in: HTTP client in which request call is made
        :param submission_factory: The factory that creates and deletes submissions
        """
        submission_id, _ = await submission_factory("Bigpicture")

        await post_object(client_logged_in, "bpsample", submission_id, "samples.xml")
        await post_object(client_logged_in, "bpimage", submission_id, "images_single.xml")
        await post_object(client_logged_in, "bpdataset", submission_id, "dataset.xml")
        await post_object(client_logged_in, "bpobservation", submission_id, "observation.xml")
        await post_object(client_logged_in, "bpstaining", submission_id, "stainings.xml")
        await post_object(client_logged_in, "bpobserver", submission_id, "observers.xml")
        await post_object(client_logged_in, "bpannotation", submission_id, "annotation.xml")

        # TO_DO: Use datacite.xml instead json file
        doi_data_raw = await get_request_data("doi", "test_doi.json")
        await patch_submission_doi(client_logged_in, submission_id, doi_data_raw)

        await post_object(client_logged_in, "bprems", submission_id, "rems.xml")

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
            assert registration.metax_id is None
            # Check REMS
            assert registration.rems_resource_id is not None
            assert registration.rems_catalogue_id is not None
            assert registration.rems_url is not None
