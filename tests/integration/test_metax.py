"""Tests for metax integration."""

import json
import logging
from typing import Any

from metadata_backend.api.models import Registration
from tests.integration.conf import auth, metax_api, submissions_url
from tests.integration.helpers import (
    get_request_data,
    patch_submission_doi,
    patch_submission_rems,
    post_object,
    publish_submission,
)

LOG = logging.getLogger(__name__)
LOG.setLevel(logging.DEBUG)


async def test_metax_research_dataset_fega_xml(client_logged_in, submission_factory):
    """Test Metax research dataset document.

    :param client_logged_in: HTTP client in which request call is made
    :param submission_factory: The factory that creates and deletes submissions
    """
    submission_id, _ = await submission_factory("FEGA")

    for schema, filename in {
        ("study", "SRP000539.xml"),
        ("dataset", "dataset.xml"),
        ("dac", "dac.xml"),
    }:
        await post_object(client_logged_in, schema, submission_id, filename)

    doi_data_raw = await get_request_data("doi", "test_doi.json")
    await patch_submission_doi(client_logged_in, submission_id, doi_data_raw)
    rems_data = await get_request_data("dac", "dac_rems.json")
    await patch_submission_rems(client_logged_in, submission_id, rems_data)
    await post_object(client_logged_in, "policy", submission_id, "policy.json")
    await post_object(client_logged_in, "run", submission_id, "ERR000076.json")
    await publish_submission(client_logged_in, submission_id)

    async with client_logged_in.get(f"{submissions_url}/{submission_id}/registrations") as resp:
        assert resp.status == 200
        res = await resp.json()
        study_registration = Registration(**[r for r in res if r["schema"] == "study"][0])
        dataset_registration = Registration(**[r for r in res if r["schema"] == "dataset"][0])
        # Check DOI
        assert study_registration.doi is not None
        assert dataset_registration.doi is not None
        # Check that metax ID exists
        assert study_registration.metax_id is not None
        assert dataset_registration.metax_id is not None

        for registration in (study_registration, dataset_registration):
            async with client_logged_in.get(f"{metax_api}/{registration.metax_id}", auth=auth) as metax_resp:
                assert metax_resp.status == 200, f"HTTP Status code error, got {metax_resp.status}"
                metax = await metax_resp.json()
                await assert_metax(
                    metax, registration.schema_type, registration.title, registration.description, registration.doi
                )


async def test_metax_research_dataset_fega_json(client_logged_in, submission_factory):
    """Test Metax research dataset document.

    :param client_logged_in: HTTP client in which request call is made
    :param submission_factory: The factory that creates and deletes submissions
    """
    submission_id, _ = await submission_factory("FEGA")

    for schema, filename in {
        ("study", "SRP000539.json"),
        ("dataset", "dataset.json"),
        ("dac", "dac.json"),
    }:
        await post_object(client_logged_in, schema, submission_id, filename)

    doi_data_raw = await get_request_data("doi", "test_doi.json")
    await patch_submission_doi(client_logged_in, submission_id, doi_data_raw)
    rems_data = await get_request_data("dac", "dac_rems.json")
    await patch_submission_rems(client_logged_in, submission_id, rems_data)
    await post_object(client_logged_in, "policy", submission_id, "policy.json")
    await post_object(client_logged_in, "run", submission_id, "ERR000076.json")
    await publish_submission(client_logged_in, submission_id)

    async with client_logged_in.get(f"{submissions_url}/{submission_id}/registrations") as resp:
        assert resp.status == 200
        res = await resp.json()
        study_registration = Registration(**[r for r in res if r["schema"] == "study"][0])
        dataset_registration = Registration(**[r for r in res if r["schema"] == "dataset"][0])
        # Check DOI
        assert study_registration.doi is not None
        assert dataset_registration.doi is not None
        # Check that metax ID exists
        assert study_registration.metax_id is not None
        assert dataset_registration.metax_id is not None

        for registration in (study_registration, dataset_registration):
            async with client_logged_in.get(f"{metax_api}/{registration.metax_id}", auth=auth) as metax_resp:
                assert metax_resp.status == 200, f"HTTP Status code error, got {metax_resp.status}"
                metax = await metax_resp.json()
                await assert_metax(
                    metax, registration.schema_type, registration.title, registration.description, registration.doi
                )


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
