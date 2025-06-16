"""Tests with Bigpicture schemas."""

import defusedxml.ElementTree as ET

from tests.integration.conf import datacite_prefix, datacite_url, objects_url
from tests.integration.helpers import (
    announce_submission,
    create_request_data,
    create_request_json_data,
    delete_published_submission,
    get_object,
    get_xml_object,
    patch_submission_doi,
    post_data_ingestion,
    post_object,
    setup_files_for_ingestion,
)


class TestBigpicture:
    """Tests with Bigpicture schemas."""

    async def test_bpdataset_gets_doi(self, client_logged_in, submission_bigpicture, user_id, project_id, admin_token):
        """Test bp dataset has doi generated.

        :param client_logged_in: HTTP client in which request call is made
        :param submission_bigpicture: submission ID, created with the BP workflow
        :param user_id: User ID of the logged in user
        :param project_id: Project ID of the logged in user
        :param admin_token: Admin token for the logged in user
        """
        # Submit bprems
        await post_object(client_logged_in, "bprems", submission_bigpicture, "rems.xml")

        # Submit bpdataset
        dataset_id, _ = await post_object(client_logged_in, "bpdataset", submission_bigpicture, "dataset.xml")

        # Add DOI and DAC for publishing the submission
        doi_data_raw = await create_request_json_data("doi", "test_doi.json")
        await patch_submission_doi(client_logged_in, submission_bigpicture, doi_data_raw)

        await setup_files_for_ingestion(
            client_logged_in, dataset_id, submission_bigpicture, user_id, project_id, admin_token
        )
        await post_data_ingestion(client_logged_in, submission_bigpicture, admin_token)

        await announce_submission(client_logged_in, submission_bigpicture, admin_token)

        # DOI is generated in the announcing phase
        bpdataset = await get_object(client_logged_in, "bpdataset", dataset_id)
        doi = bpdataset.get("doi", "")
        assert doi.startswith(datacite_prefix)
        assert "bpdataset" in doi

        async with client_logged_in.get(f"{datacite_url}/dois/{bpdataset['doi']}") as datacite_resp:
            assert datacite_resp.status == 200, f"HTTP Status code error, got {datacite_resp.status}"

        # Attempt to delete a published submission
        await delete_published_submission(client_logged_in, submission_bigpicture)

    async def test_get_bpsample_with_accession_id(self, client_logged_in, submission_bigpicture):
        """Test bp samples can be retrieved with accession ids.

        :param client_logged_in: HTTP client in which request call is made
        :param submission_bigpicture: submission ID, created with the BP workflow
        """

        # Submit samples
        bpsamples, _ = await post_object(client_logged_in, "bpsample", submission_bigpicture, "samples.xml")

        # Retrieve samples with accession ids
        for sample in bpsamples:
            bpsample = await get_object(client_logged_in, "bpsample", sample["accessionId"])
            assert bpsample["accessionId"] == sample["accessionId"], "Wrong metadata object was returned"

            # Check the XML content was altered and stored correctly as well
            bpsample_xml = await get_xml_object(client_logged_in, "bpsample", sample["accessionId"])
            root = ET.fromstring(bpsample_xml)
            assert root.tag == "SAMPLE_SET"
            child_elements = list(root)
            assert len(child_elements) == 1, "Wrong number of child elements found"
            tags = ["BIOLOGICAL_BEING", "CASE", "SPECIMEN", "SLIDE", "BLOCK"]
            assert child_elements[0].tag in tags, "Wrong child element was found"
            child_attributes = child_elements[0].attrib
            assert child_attributes["accession"] == sample["accessionId"], "Wrong accession ID was stored in XML"

    async def test_bpdataset_replace_fails(self, client_logged_in, submission_bigpicture):
        """Test bp dataset PUT fails when accession id is missing in XML.

        :param client_logged_in: HTTP client in which request call is made
        :param submission_bigpicture: submission ID, created with the BP workflow
        """
        # Submit bpdataset
        accession_id, _ = await post_object(client_logged_in, "bpdataset", submission_bigpicture, "dataset.xml")

        # Verify accession id was added to dataset object
        bpdataset_data = await get_object(client_logged_in, "bpdataset", accession_id)
        assert bpdataset_data.get("accessionId", "") == accession_id

        # Attempt to replace object without accession id in xml
        request_data = await create_request_data("bpdataset", "dataset.xml")
        async with client_logged_in.put(f"{objects_url}/bpdataset/{accession_id}", data=request_data) as resp:
            assert resp.status == 400
            res = await resp.json()
            assert "accession" in res["detail"]
