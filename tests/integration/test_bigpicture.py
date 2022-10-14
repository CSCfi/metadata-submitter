"""Tests with big picture schemas."""
from tests.integration.conf import datacite_url
from tests.integration.helpers import (
    create_request_json_data,
    delete_published_submission,
    get_object,
    post_object,
    post_object_json,
    publish_submission,
    put_submission_dac,
    put_submission_doi,
)


class TestBigPicture:
    """Tests with big picture schemas."""

    async def test_bpdataset_gets_doi(self, client_logged_in, submission_bigpicture):
        """Test bp dataset has doi generated.

        :param client_logged_in: HTTP client in which request call is made
        :param submission_bigpicture: submission ID, created with the BP workflow
        """

        # Submit study, bpdataset
        study = await post_object_json(client_logged_in, "study", submission_bigpicture, "SRP000539.json")
        bpdataset = await post_object(client_logged_in, "bpdataset", submission_bigpicture, "template_dataset.xml")

        # Add DOI and DAC for publishing the submission
        doi_data_raw = await create_request_json_data("doi", "test_doi.json")
        await put_submission_doi(client_logged_in, submission_bigpicture, doi_data_raw)

        dac_data = await create_request_json_data("dac", "dac_rems.json")
        await put_submission_dac(client_logged_in, submission_bigpicture, dac_data)

        await publish_submission(client_logged_in, submission_bigpicture)

        # DOI is generated in the publishing phase
        bpdataset = await get_object(client_logged_in, "bpdataset", bpdataset[0])
        assert bpdataset.get("doi") is not None

        # check that datacite has references between datasets and study
        async with client_logged_in.get(f"{datacite_url}/dois/{bpdataset['doi']}") as datacite_resp:
            assert datacite_resp.status == 200, f"HTTP Status code error, got {datacite_resp.status}"
            datacite_res = await datacite_resp.json()
            bpdataset = datacite_res

        study = await get_object(client_logged_in, "study", study)
        assert study.get("doi") is not None
        async with client_logged_in.get(f"{datacite_url}/dois/{study['doi']}") as datacite_resp:
            assert datacite_resp.status == 200, f"HTTP Status code error, got {datacite_resp.status}"
            datacite_res = await datacite_resp.json()
            study = datacite_res
        assert bpdataset["data"]["attributes"]["relatedIdentifiers"][0]["relatedIdentifier"] == study["id"]
        for _ in study["data"]["attributes"]["relatedIdentifiers"]:
            assert study["data"]["attributes"]["relatedIdentifiers"][0]["relatedIdentifier"] == bpdataset["id"]

        # Attempt to delete a published submission
        await delete_published_submission(client_logged_in, submission_bigpicture)
