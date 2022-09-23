"""Tests with big picture schemas."""
from tests.integration.conf import datacite_url
from tests.integration.helpers import (
    create_request_json_data,
    delete_submission_publish,
    get_object,
    post_object,
    post_object_json,
    post_submission,
    publish_submission,
    put_submission_dac,
    put_submission_doi,
)


class TestBigPicture:
    """Tests with big picture schemas."""

    async def test_bpdataset_gets_doi(self, client_logged_in, project_id):
        """Test bp dataset has doi generated.

        :param client_logged_in: HTTP client in which request call is made
        :param project_id: id of the project the submission belongs to
        """
        # Create new submission
        submission_data = {
            "name": "Test bpdataset submission",
            "description": "Test that DOI is generated for bp dataset",
            "projectId": project_id,
        }
        submission_id = await post_submission(client_logged_in, submission_data)

        # Submit study, bpdataset
        study = await post_object_json(client_logged_in, "study", submission_id, "SRP000539.json")
        study = await get_object(client_logged_in, "study", study)

        bpdataset = await post_object(client_logged_in, "bpdataset", submission_id, "template_dataset.xml")
        bpdataset = await get_object(client_logged_in, "bpdataset", bpdataset[0])
        assert bpdataset["doi"] is not None

        # Add DOI for publishing the submission
        doi_data_raw = await create_request_json_data("doi", "test_doi.json")
        await put_submission_doi(client_logged_in, submission_id, doi_data_raw)

        dac_data = await create_request_json_data("dac", "dac_rems.json")
        await put_submission_dac(client_logged_in, submission_id, dac_data)

        submission_id = await publish_submission(client_logged_in, submission_id)

        # check that datacite has references between datasets and study
        async with client_logged_in.get(f"{datacite_url}/dois/{bpdataset['doi']}") as datacite_resp:
            assert datacite_resp.status == 200, f"HTTP Status code error, got {datacite_resp.status}"
            datacite_res = await datacite_resp.json()
            bpdataset = datacite_res

        async with client_logged_in.get(f"{datacite_url}/dois/{study['doi']}") as datacite_resp:
            assert datacite_resp.status == 200, f"HTTP Status code error, got {datacite_resp.status}"
            datacite_res = await datacite_resp.json()
            study = datacite_res
        assert bpdataset["data"]["attributes"]["relatedIdentifiers"][0]["relatedIdentifier"] == study["id"]
        for _ in study["data"]["attributes"]["relatedIdentifiers"]:
            assert study["data"]["attributes"]["relatedIdentifiers"][0]["relatedIdentifier"] == bpdataset["id"]

        # Delete submission
        await delete_submission_publish(client_logged_in, submission_id)
