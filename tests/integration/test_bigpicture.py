"""Tests with big picture schemas."""

import defusedxml.ElementTree as ET

from tests.integration.conf import datacite_prefix, datacite_url
from tests.integration.helpers import (
    announce_submission,
    create_request_json_data,
    delete_published_submission,
    get_object,
    get_xml_object,
    patch_submission_doi,
    post_object,
)


class TestBigPicture:
    """Tests with big picture schemas."""

    async def test_bpdataset_gets_doi(self, client_logged_in, submission_bigpicture, project_id):
        """Test bp dataset has doi generated.

        :param client_logged_in: HTTP client in which request call is made
        :param submission_bigpicture: submission ID, created with the BP workflow
        """
        # Submit bprems
        await post_object(client_logged_in, "bprems", submission_bigpicture, "rems.xml")

        # Submit bpdataset
        bpdataset = await post_object(client_logged_in, "bpdataset", submission_bigpicture, "dataset.xml")

        # Add DOI and DAC for publishing the submission
        doi_data_raw = await create_request_json_data("doi", "test_doi.json")
        await patch_submission_doi(client_logged_in, submission_bigpicture, doi_data_raw)

        await announce_submission(client_logged_in, submission_bigpicture)

        # DOI is generated in the announcing phase
        bpdataset = await get_object(client_logged_in, "bpdataset", bpdataset[0])
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
