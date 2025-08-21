"""Tests with Bigpicture schemas."""

import defusedxml.ElementTree as ET

from metadata_backend.api.models import Registration
from tests.integration.conf import datacite_prefix, datacite_url
from tests.integration.helpers import (
    get_object,
    get_request_data,
    get_xml_object,
    patch_submission_doi,
    post_object,
    publish_submission,
    put_object,
    submissions_url,
)


class TestBigpicture:
    """Tests with Bigpicture schemas."""

    async def test_bpdataset_gets_doi(self, client_logged_in, submission_factory):
        """Test bp dataset has doi generated.

        :param client_logged_in: HTTP client in which request call is made
        :param submission_factory: The factory that creates and deletes submissions
        """
        submission_id, _ = await submission_factory("Bigpicture")

        await post_object(client_logged_in, "bprems", submission_id, "rems.xml")
        await post_object(client_logged_in, "bpdataset", submission_id, "dataset.xml")

        # Add DOI and DAC for publishing the submission
        doi_data_raw = await get_request_data("doi", "test_doi.json")
        await patch_submission_doi(client_logged_in, submission_id, doi_data_raw)

        await publish_submission(client_logged_in, submission_id)

        # DOI is generated in the publishing phase
        async with client_logged_in.get(f"{submissions_url}/{submission_id}/registrations") as resp:
            assert resp.status == 200
            res = await resp.json()
            registration = Registration(**res[0])
            # Check DOI
            assert registration.doi.startswith(datacite_prefix)

        async with client_logged_in.get(f"{datacite_url}/dois/{registration.doi}") as datacite_resp:
            assert datacite_resp.status == 200, f"HTTP Status code error, got {datacite_resp.status}"

    async def test_get_bpsample_with_accession_id(self, client_logged_in, submission_factory):
        """Test bp samples can be retrieved with accession ids.

        :param client_logged_in: HTTP client in which request call is made
        :param submission_factory: The factory that creates and deletes submissions
        """
        submission_id, _ = await submission_factory("Bigpicture")

        # Submit samples
        sample_id = await post_object(client_logged_in, "bpsample", submission_id, "samples.xml")

        bpsample = await get_object(client_logged_in, "bpsample", sample_id)
        assert bpsample["accessionId"] == sample_id, "Wrong metadata object was returned"

        # Check the XML content was altered and stored correctly as well
        bpsample_xml = await get_xml_object(client_logged_in, "bpsample", sample_id)
        root = ET.fromstring(bpsample_xml)
        assert root.tag == "SAMPLE_SET"
        child_elements = list(root)
        assert len(child_elements) == 1, "Wrong number of child elements found"
        tags = ["BIOLOGICAL_BEING", "CASE", "SPECIMEN", "SLIDE", "BLOCK"]
        assert child_elements[0].tag in tags, "Wrong child element was found"
        child_attributes = child_elements[0].attrib
        assert child_attributes["accession"] == sample_id, "Wrong accession ID was stored in XML"

    async def test_bpdataset_replace_fails(self, client_logged_in, submission_factory):
        """Test bp dataset PUT fails when accession id is missing in XML.

        :param client_logged_in: HTTP client in which request call is made
        :param submission_factory: The factory that creates and deletes submissions
        """
        submission_id, _ = await submission_factory("Bigpicture")

        # Submit bpdataset
        accession_id = await post_object(client_logged_in, "bpdataset", submission_id, "dataset.xml")

        # Verify accession id was added to dataset object
        bpdataset_data = await get_object(client_logged_in, "bpdataset", accession_id)
        assert bpdataset_data.get("accessionId", "") == accession_id

        # Attempt to replace object without accession id in xml
        await put_object(client_logged_in, "bpdataset", accession_id, "dataset.xml")
