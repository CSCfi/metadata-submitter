"""Smoke test publications."""

import logging

from tests.integration.conf import metax_api, metax_discovery_url, objects_url, submissions_url
from tests.integration.helpers import (
    announce_submission,
    create_request_json_data,
    post_object,
    post_object_json,
    publish_submission,
    put_submission_doi,
    put_submission_rems,
)

LOG = logging.getLogger(__name__)
LOG.setLevel(logging.DEBUG)


class TestMinimalPublication:
    """Test minimal publication with JSON submissions for FEGA and SDSX workflows, XML submissions for BP workflow."""

    async def test_minimal_fega_json_publication(self, client_logged_in, submission_fega):
        """Test minimal FEGA publication workflow with JSON submissions.

        :param client_logged_in: HTTP client in which request call is made
        :param submission_fega: submission ID, created with the fega workflow
        """
        await post_object_json(client_logged_in, "study", submission_fega, "SRP000539.json")
        doi_data_raw = await create_request_json_data("doi", "test_doi.json")
        await put_submission_doi(client_logged_in, submission_fega, doi_data_raw)
        rems_data = await create_request_json_data("dac", "dac_rems.json")
        await put_submission_rems(client_logged_in, submission_fega, rems_data)
        await post_object_json(client_logged_in, "policy", submission_fega, "policy.json")
        await post_object_json(client_logged_in, "run", submission_fega, "ERR000076.json")
        await post_object_json(client_logged_in, "dataset", submission_fega, "dataset.json")
        await publish_submission(client_logged_in, submission_fega)

        async with client_logged_in.get(f"{submissions_url}/{submission_fega}") as resp:
            LOG.debug("Checking that submission %s was published", submission_fega)
            res = await resp.json()
            assert res["submissionId"] == submission_fega, "expected submission id does not match"
            assert res["published"] is True, "submission is published, expected False"
            # Check that discovery service for publication is correct
            assert res["extraInfo"]["studyIdentifier"]["url"].startswith(metax_discovery_url)

    async def test_minimal_sdsx_json_publication(self, client_logged_in, submission_sdsx):
        """Test minimal SDSX publication workflow with JSON submissions.

        :param client_logged_in: HTTP client in which request call is made
        :param submission_sdsx: submission ID, created with the sdsx workflow
        """
        doi_data_raw = await create_request_json_data("doi", "test_doi.json")
        await put_submission_doi(client_logged_in, submission_sdsx, doi_data_raw)
        rems_data = await create_request_json_data("dac", "dac_rems.json")
        await put_submission_rems(client_logged_in, submission_sdsx, rems_data)
        await post_object_json(client_logged_in, "dataset", submission_sdsx, "dataset.json")
        await publish_submission(client_logged_in, submission_sdsx)

        async with client_logged_in.get(f"{submissions_url}/{submission_sdsx}") as resp:
            LOG.debug(f"Checking that submission {submission_sdsx} was published")
            res = await resp.json()
            assert res["submissionId"] == submission_sdsx, "expected submission id does not match"
            assert res["published"] is True, "submission is published, expected False"

    async def test_minimal_bigpicture_xml_publication(self, client_logged_in, submission_bigpicture):
        """Test minimal BP publication workflow with XML submissions.

        :param client_logged_in: HTTP client in which request call is made
        :param submission_bigpicture: submission ID, created with the sdsx workflow
        """
        # TO_DO: User datacite.xml instead json file
        doi_data_raw = await create_request_json_data("doi", "test_doi.json")
        await put_submission_doi(client_logged_in, submission_bigpicture, doi_data_raw)

        await post_object(client_logged_in, "bprems", submission_bigpicture, "rems.xml")
        await announce_submission(client_logged_in, submission_bigpicture)

        async with client_logged_in.get(f"{submissions_url}/{submission_bigpicture}") as resp:
            LOG.debug(f"Checking that submission {submission_bigpicture} was published")
            res = await resp.json()
            assert res["submissionId"] == submission_bigpicture, "expected submission id does not match"
            assert res["published"] is True, "submission is published, expected False"


class TestMinimalPublicationRems:
    """Test minimal publication to REMS."""

    async def test_minimal_fega_json_publication_rems(self, client_logged_in, submission_fega):
        """Test minimal FEGA publication workflow with JSON submissions to REMS.

        :param client_logged_in: HTTP client in which request call is made
        :param submission_fega: submission ID, created with the fega workflow
        """
        await post_object_json(client_logged_in, "study", submission_fega, "SRP000539.json")
        dataset_id = await post_object_json(client_logged_in, "dataset", submission_fega, "dataset.json")
        await post_object_json(client_logged_in, "run", submission_fega, "ERR000076.json")

        doi_data_raw = await create_request_json_data("doi", "test_doi.json")
        await put_submission_doi(client_logged_in, submission_fega, doi_data_raw)

        rems_data = await create_request_json_data("dac", "dac_rems.json")
        await put_submission_rems(client_logged_in, submission_fega, rems_data)
        await post_object_json(client_logged_in, "policy", submission_fega, "policy.json")
        await publish_submission(client_logged_in, submission_fega)

        async with client_logged_in.get(f"{submissions_url}/{submission_fega}") as resp:
            LOG.debug("Checking that submission %s was published", submission_fega)
            res = await resp.json()
            assert res["submissionId"] == submission_fega, "expected submission id does not match"
            assert res["published"] is True, "submission is published, expected False"

        async with client_logged_in.get(f"{objects_url}/dataset/{dataset_id}") as resp:
            LOG.debug("Checking that dataset %s in submission %s has rems data", dataset_id, submission_fega)
            res = await resp.json()
            assert res["accessionId"] == dataset_id, "expected dataset id does not match"
            assert "internal_rems" in res, "expected internal_rems field not found in dataset"
            assert "url" in res["internal_rems"], "expected url not found in internal_rems field"
            assert "resourceId" in res["internal_rems"], "expected resourceId not found in internal_rems field"
            assert "catalogueId" in res["internal_rems"], "expected catalogueId not found in internal_rems field"

    async def test_minimal_bigpicture_xml_publication_rems(self, client_logged_in, submission_bigpicture, database):
        """Test minimal BP publication workflow with XML submissions to REMS.

        :param client_logged_in: HTTP client in which request call is made
        :param submission_bigpicture: submission ID, created with the fega workflow
        """
        dataset_id, _ = await post_object(client_logged_in, "bpdataset", submission_bigpicture, "dataset.xml")
        # TO_DO: User datacite.xml instead json file
        doi_data_raw = await create_request_json_data("doi", "test_doi.json")
        await put_submission_doi(client_logged_in, submission_bigpicture, doi_data_raw)

        await post_object(client_logged_in, "bprems", submission_bigpicture, "rems.xml")

        await announce_submission(client_logged_in, submission_bigpicture)

        async with client_logged_in.get(f"{submissions_url}/{submission_bigpicture}") as resp:
            LOG.debug(f"Checking that submission {submission_bigpicture} was published")
            res = await resp.json()
            assert res["submissionId"] == submission_bigpicture, "expected submission id does not match"
            assert res["published"] is True, "submission is published, expected False"

        async with client_logged_in.get(f"{objects_url}/bpdataset/{dataset_id}") as resp:
            LOG.debug(f"Checking that dataset {dataset_id} in submission {submission_bigpicture} has rems data")
            res = await resp.json()
            assert res["accessionId"] == dataset_id, "expected dataset id does not match"
            assert "internal_rems" in res, "expected internal_rems field not found in dataset"
            assert "url" in res["internal_rems"], "expected url not found in internal_rems field"
            assert "resourceId" in res["internal_rems"], "expected resourceId not found in internal_rems field"
            assert "catalogueId" in res["internal_rems"], "expected catalogueId not found in internal_rems field"


class TestFullPublication:
    """Test full publication to Metax and REMS."""

    async def test_full_fega_json_publication_rems(self, client_logged_in, submission_fega):
        """Test minimal FEGA publication workflow with JSON submissions to Metax and REMS.

        :param client_logged_in: HTTP client in which request call is made
        :param submission_fega: submission ID, created with the fega workflow
        """
        objects = []
        study_id = await post_object_json(client_logged_in, "study", submission_fega, "SRP000539.json")
        objects.append(["study", study_id])

        await post_object_json(client_logged_in, "dac", submission_fega, "dac.json")
        await post_object_json(client_logged_in, "policy", submission_fega, "policy.json")
        await post_object_json(client_logged_in, "sample", submission_fega, "SRS001433.json")
        await post_object_json(client_logged_in, "experiment", submission_fega, "ERX000119.json")
        await post_object_json(client_logged_in, "analysis", submission_fega, "ERZ266973.json")
        await post_object_json(client_logged_in, "run", submission_fega, "ERR000076.json")

        dataset_id = await post_object_json(client_logged_in, "dataset", submission_fega, "dataset.json")
        objects.append(["dataset", dataset_id])

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

        for schema, object_id in objects:
            async with client_logged_in.get(f"{objects_url}/{schema}/{object_id}") as resp:
                res = await resp.json()
                LOG.debug(f"Checking that {schema} {object_id} in submission {submission_fega} published to Datacite")
                doi = res.get("doi", "")
                assert doi != ""
                metax_id = res.get("metaxIdentifier", "")
                assert metax_id != ""

            async with client_logged_in.get(f"{metax_api}/{metax_id}") as metax_resp:
                LOG.debug(f"Checking that {schema} with metaxIdentifier {metax_id} was published to Metax")
                assert resp.status == 200, f"HTTP Status code error, got {resp.status}"
                metax_res = await metax_resp.json()
                assert metax_res["research_dataset"]["preferred_identifier"] == doi

        async with client_logged_in.get(f"{objects_url}/dataset/{dataset_id}") as resp:
            LOG.debug(f"Checking that dataset {dataset_id} in submission {submission_fega} has rems data")
            res = await resp.json()
            assert res["accessionId"] == dataset_id, "expected dataset id does not match"
            assert "internal_rems" in res, "expected internal_rems field not found in dataset"
            assert "url" in res["internal_rems"], "expected url not found in internal_rems field"
            assert "resourceId" in res["internal_rems"], "expected resourceId not found in internal_rems field"
            assert "catalogueId" in res["internal_rems"], "expected catalogueId not found in internal_rems field"

    async def test_full_sdsx_json_publication_rems(self, client_logged_in, submission_sdsx):
        """Test minimal FEGA publication workflow with JSON submissions to Metax and REMS.

        :param client_logged_in: HTTP client in which request call is made
        :param submission_sdsx: submission ID, created with the fega workflow
        """
        objects = []

        rems_data = await create_request_json_data("dac", "dac_rems.json")
        await put_submission_rems(client_logged_in, submission_sdsx, rems_data)

        dataset_id = await post_object_json(client_logged_in, "dataset", submission_sdsx, "dataset.json")
        objects.append(["dataset", dataset_id])

        doi_data_raw = await create_request_json_data("doi", "test_doi.json")
        await put_submission_doi(client_logged_in, submission_sdsx, doi_data_raw)

        await publish_submission(client_logged_in, submission_sdsx)

        async with client_logged_in.get(f"{submissions_url}/{submission_sdsx}") as resp:
            LOG.debug(f"Checking that submission {submission_sdsx} was published")
            res = await resp.json()
            assert res["submissionId"] == submission_sdsx, "expected submission id does not match"
            assert res["published"] is True, "submission is published, expected False"

        for schema, object_id in objects:
            async with client_logged_in.get(f"{objects_url}/{schema}/{object_id}") as resp:
                res = await resp.json()
                LOG.debug(f"Checking that {schema} {object_id} in submission {submission_sdsx} published to Datacite")
                doi = res.get("doi", "")
                assert doi != ""
                metax_id = res.get("metaxIdentifier", "")
                assert metax_id != ""

            async with client_logged_in.get(f"{metax_api}/{metax_id}") as metax_resp:
                LOG.debug(f"Checking that {schema} with metaxIdentifier {metax_id} was published to Metax")
                assert resp.status == 200, f"HTTP Status code error, got {resp.status}"
                metax_res = await metax_resp.json()
                assert metax_res["research_dataset"]["preferred_identifier"] == doi

        async with client_logged_in.get(f"{objects_url}/dataset/{dataset_id}") as resp:
            LOG.debug(f"Checking that dataset {dataset_id} in submission {submission_sdsx} has rems data")
            res = await resp.json()
            assert res["accessionId"] == dataset_id, "expected dataset id does not match"
            assert "internal_rems" in res, "expected internal_rems field not found in dataset"
            assert "url" in res["internal_rems"], "expected url not found in internal_rems field"
            assert "resourceId" in res["internal_rems"], "expected resourceId not found in internal_rems field"
            assert "catalogueId" in res["internal_rems"], "expected catalogueId not found in internal_rems field"

    async def test_full_bigpicture_xml_publication_rems(self, client_logged_in, submission_bigpicture):
        """Test full BP publication workflow with XML submissions to REMS.

        :param client_logged_in: HTTP client in which request call is made
        :param submission_bigpicture: submission ID, created with the fega workflow
        """
        await post_object(client_logged_in, "bpsample", submission_bigpicture, "samples.xml")
        await post_object(client_logged_in, "bpimage", submission_bigpicture, "images_single.xml")
        dataset_id, _ = await post_object(client_logged_in, "bpdataset", submission_bigpicture, "dataset.xml")
        await post_object(client_logged_in, "bpobservation", submission_bigpicture, "observations.xml")
        await post_object(client_logged_in, "bpstaining", submission_bigpicture, "stainings.xml")
        await post_object(client_logged_in, "bpobserver", submission_bigpicture, "observers.xml")
        await post_object(client_logged_in, "bpannotation", submission_bigpicture, "annotations.xml")

        # TO_DO: User datacite.xml instead json file
        doi_data_raw = await create_request_json_data("doi", "test_doi.json")
        await put_submission_doi(client_logged_in, submission_bigpicture, doi_data_raw)

        await post_object(client_logged_in, "bprems", submission_bigpicture, "rems.xml")

        await announce_submission(client_logged_in, submission_bigpicture)

        async with client_logged_in.get(f"{submissions_url}/{submission_bigpicture}") as resp:
            LOG.debug(f"Checking that submission {submission_bigpicture} was published")
            res = await resp.json()
            assert res["submissionId"] == submission_bigpicture, "expected submission id does not match"
            assert res["published"] is True, "submission is published, expected False"

        async with client_logged_in.get(f"{objects_url}/bpdataset/{dataset_id}") as resp:
            res = await resp.json()
            LOG.debug(
                f"Checking that bpdataset {dataset_id} in submission {submission_bigpicture} published to Datacite"
            )
            doi = res.get("doi", "")
            assert doi != ""

            LOG.debug(f"Checking that metaxIdentifier do not exist in bpdataset {dataset_id}")
            metax_id = res.get("metaxIdentifier", "")
            assert metax_id == ""

            LOG.debug(f"Checking that dataset {dataset_id} in submission {submission_bigpicture} has rems data")
            assert res["accessionId"] == dataset_id, "expected dataset id does not match"
            assert "internal_rems" in res, "expected internal_rems field not found in dataset"
            assert "url" in res["internal_rems"], "expected url not found in internal_rems field"
            assert "resourceId" in res["internal_rems"], "expected resourceId not found in internal_rems field"
            assert "catalogueId" in res["internal_rems"], "expected catalogueId not found in internal_rems field"
