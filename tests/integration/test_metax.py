"""Tests for metax integration."""
import json
import logging

from tests.integration.conf import auth, metax_api, objects_url
from tests.integration.helpers import (
    create_request_json_data,
    delete_object,
    patch_object_json,
    post_object,
    post_object_json,
    publish_submission,
    put_object_json,
    put_object_xml,
    put_submission_dac,
    put_submission_doi,
)

LOG = logging.getLogger(__name__)
LOG.setLevel(logging.DEBUG)


async def test_metax_id_created(client_logged_in, submission_fega):
    """Test Metax service with study and dataset xml files POST, PUBLISH reqs.

    :param client_logged_in: HTTP client in which request call is made
    :param submission_fega: id of the submission where objects reside
    """
    # POST to object endpoint creates draft dataset in Metax for Study and Dataset
    ids = []
    xml_files = set()
    for schema, filename, update_filename in {
        ("study", "SRP000539.xml", "SRP000539_put.xml"),
        ("dataset", "dataset.xml", "dataset_put.xml"),
    }:
        accession_id, _ = await post_object(client_logged_in, schema, submission_fega, filename)
        xml_files.add((schema, accession_id, update_filename))
        ids.append([schema, accession_id])

    doi_data_raw = await create_request_json_data("doi", "test_doi.json")
    await put_submission_doi(client_logged_in, submission_fega, doi_data_raw)
    # dac_data = await create_request_json_data("dac", "dac_rems.json")
    # await put_submission_dac(client_logged_in, submission_fega, dac_data)
    await post_object_json(client_logged_in, "run", submission_fega, "ERR000076.json")
    await publish_submission(client_logged_in, submission_fega)

    for object in ids:
        schema, accession_id = object
        async with client_logged_in.get(f"{objects_url}/{schema}/{accession_id}") as resp:
            assert resp.status == 200, f"HTTP Status code error, got {resp.status}"
            res = await resp.json()
            try:
                metax_id = res["metaxIdentifier"]
            except KeyError:
                assert False, "Metax ID was not in response data"
        object.append(metax_id)
        async with client_logged_in.get(f"{metax_api}/{metax_id}", auth=auth) as metax_resp:
            assert metax_resp.status == 200, f"HTTP Status code error, got {metax_resp.status}"
            metax_res = await metax_resp.json()
            assert (
                res.get("doi", None) == metax_res["research_dataset"]["preferred_identifier"]
            ), "Object's DOI was not in Metax response data preferred_identifier"


async def test_metax_crud_with_xml(client_logged_in, submission_fega):
    """Test Metax service with study and dataset xml files POST, PATCH, PUBLISH and DELETE reqs.

    :param client_logged_in: HTTP client in which request call is made
    :param submission_fega: id of the submission where objects reside
    """
    # POST to object endpoint creates draft dataset in Metax for Study and Dataset
    ids = []
    xml_files = set()
    for schema, filename, update_filename in {
        ("study", "SRP000539.xml", "SRP000539_put.xml"),
        ("dataset", "dataset.xml", "dataset_put.xml"),
    }:
        accession_id, _ = await post_object(client_logged_in, schema, submission_fega, filename)
        xml_files.add((schema, accession_id, update_filename))
        ids.append([schema, accession_id])

    # PUT and PATCH to object endpoint updates draft dataset in Metax for Study and Dataset
    for schema, accession_id, filename in xml_files:
        await put_object_xml(client_logged_in, schema, accession_id, filename)

    # for _, _, metax_id in ids:
    #     async with client_logged_in.get(f"{metax_api}/{metax_id}", auth=auth) as metax_resp:
    #         assert metax_resp.status == 200, f"HTTP Status code error, got {metax_resp.status}"
    #         metax_res = await metax_resp.json()
    #         assert (
    #             metax_res.get("date_modified", None) is not None
    #         ), f"Object with metax id {metax_res['identifier']} was not updated in Metax"
    #
    # # DELETE object from Metax
    # for schema, accession_id, _ in xml_files:
    #     await delete_object(client_logged_in, schema, accession_id)
    #
    # for _, _, metax_id in ids:
    #     async with client_logged_in.get(f"{metax_api}/{metax_id}", auth=auth) as metax_resp:
    #         assert (
    #             metax_resp.status == 404
    #         ), f"HTTP Status code error - expected 404 Not Found, got {metax_resp.status}"


async def test_metax_crud_with_json(client_logged_in, submission_fega):
    """Test Metax service with study and dataset json data POST, PATCH, PUBLISH and DELETE reqs.

    :param client_logged_in: HTTP client in which request call is made
    :param submission_fega: id of the submission where objects reside
    """
    ids = []
    json_files = set()
    for schema, filename, update_filename in {
        ("study", "SRP000539.json", "patch.json"),
        ("dataset", "dataset.json", "dataset_patch.json"),
    }:
        accession_id = await post_object_json(client_logged_in, schema, submission_fega, filename)
        json_files.add((schema, accession_id, filename, update_filename))
        ids.append([schema, accession_id])

    for object in ids:
        schema, accession_id = object
        async with client_logged_in.get(f"{objects_url}/{schema}/{accession_id}") as resp:
            assert resp.status == 200, f"HTTP Status code error, got {resp.status}"
            # res = await resp.json()
            # try:
            #     metax_id = res["metaxIdentifier"]
            # except KeyError:
            #     assert False, "Metax ID was not in response data"
        # object.append(metax_id)
        # async with client_logged_in.get(f"{metax_api}/{metax_id}", auth=auth) as metax_resp:
        #     assert metax_resp.status == 200, f"HTTP Status code error, got {metax_resp.status}"
        #     metax_res = await metax_resp.json()
        #     assert (
        #         res.get("doi", None) == metax_res["research_dataset"]["preferred_identifier"]
        #     ), "Object's DOI was not in Metax response data preferred_identifier"

    for schema, accession_id, filename, _ in json_files:
        await put_object_json(client_logged_in, schema, accession_id, filename)
    for schema, accession_id, _, filename in json_files:
        await patch_object_json(client_logged_in, schema, accession_id, filename)

    for schema, accession_id, _, _ in json_files:
        await delete_object(client_logged_in, schema, accession_id)


async def test_metax_id_not_updated_on_patch(client_logged_in, submission_fega):
    """Test that Metax id cannot be sent in patch.

    :param client_logged_in: HTTP client in which request call is made
    :param submission_fega: id of the submission where objects reside
    """
    for schema, filename in {
        ("study", "SRP000539.json"),
        ("dataset", "dataset.json"),
    }:
        accession_id = await post_object_json(client_logged_in, schema, submission_fega, filename)
        async with client_logged_in.patch(
            f"{objects_url}/{schema}/{accession_id}",
            data={"metaxIdentifier": "12345"},
        ) as resp:
            LOG.debug(f"Trying to patch object in {schema}")
            assert resp.status == 400

            await delete_object(client_logged_in, schema, accession_id)


async def test_metax_publish_dataset(client_logged_in, submission_fega):
    """Test publishing dataset to Metax service after submission is published.

    :param client_logged_in: HTTP client in which request call is made
    :param submission_fega: id of the submission where objects reside
    """
    # POST to object endpoint creates draft dataset in Metax for Study and Dataset
    objects = []
    for schema, filename in {
        ("study", "SRP000539.xml"),
        ("dataset", "dataset.xml"),
    }:
        accession_id, _ = await post_object(client_logged_in, schema, submission_fega, filename)
        objects.append([schema, accession_id])

    for object in objects:
        schema, object_id = object
        async with client_logged_in.get(f"{objects_url}/{schema}/{object_id}") as resp:
            assert resp.status == 200, f"HTTP Status code error, got {resp.status}"
            res = await resp.json()
            # object.append(res["metaxIdentifier"])

    # Add DOI and publish the submission
    doi_data_raw = await create_request_json_data("doi", "test_doi.json")
    await put_submission_doi(client_logged_in, submission_fega, doi_data_raw)
    dac_data = await create_request_json_data("dac", "dac_rems.json")
    await put_submission_dac(client_logged_in, submission_fega, dac_data)
    await post_object_json(client_logged_in, "run", submission_fega, "ERR000076.json")
    await publish_submission(client_logged_in, submission_fega)

    metax_ids = []
    for schema, object_id in objects:
        async with client_logged_in.get(f"{objects_url}/{schema}/{object_id}") as resp:
            assert resp.status == 200, f"HTTP Status code error, got {resp.status}"
            res = await resp.json()
            metax_id = res.get("metaxIdentifier", "")
            assert metax_id != ""
            metax_ids.append(metax_id)

        async with client_logged_in.get(f"{metax_api}/{metax_id}") as metax_resp:
            assert metax_resp.status == 200, f"HTTP Status code error, got {metax_resp.status}"
            metax_res = await metax_resp.json()
            assert metax_res["state"] == "published", f"{schema}  {metax_res}"

            # this data is synced with /test_files/doi/test_doi.json
            # if data changes inside the file it must be reflected here
            expected_rd = json.loads(await create_request_json_data("metax", "research_dataset.json"))
            actual_rd = metax_res["research_dataset"]

            title = res["title"] if schema == "dataset" else res["descriptor"]["studyTitle"]
            description = res["description"] if schema == "dataset" else res["descriptor"]["studyAbstract"]

            assert actual_rd["title"]["en"] == title
            assert actual_rd["description"]["en"].split("\n\n")[0] == description
            assert actual_rd["creator"] == expected_rd["creator"]
            assert (
                actual_rd["access_rights"]["access_type"]["identifier"]
                == expected_rd["access_rights"]["access_type"]["identifier"]
            )
            assert actual_rd["contributor"] == expected_rd["contributor"]
            assert actual_rd["curator"] == expected_rd["curator"]
            assert actual_rd["issued"] == expected_rd["issued"]
            assert actual_rd["modified"] == expected_rd["modified"]
            assert actual_rd["other_identifier"][0]["notation"] == expected_rd["other_identifier"][0]["notation"]
            assert actual_rd["publisher"] == expected_rd["publisher"]
            assert actual_rd["rights_holder"] == expected_rd["rights_holder"]
            assert actual_rd["spatial"] == expected_rd["spatial"]
            assert actual_rd["temporal"] == expected_rd["temporal"]
            assert actual_rd["language"] == expected_rd["language"]
            assert actual_rd["field_of_science"] == expected_rd["field_of_science"]

            if schema == "study":
                assert "relation" in actual_rd
                # study_dataset_relation = actual_rd["relation"][0]["entity"]["identifier"].split("/")[-1]
                study_metax_id = metax_id
            if schema == "dataset":
                assert "is_output_of" in actual_rd
                dataset_output_study = actual_rd["is_output_of"][0]["identifier"].split("/")[-1]
                # dataset_metax_id = metax_id

    # assert study_dataset_relation == dataset_metax_id
    assert dataset_output_study == study_metax_id

    for (_, _), metax_id in zip(objects, metax_ids):
        # delete of published metax datasets is possible only from mocked metax for testing purpose
        # Metax service does not allow deleting published datasets
        await client_logged_in.delete(f"{metax_api}/{metax_id}", params={"test": "true"})


# class TestMetaxMissingId:
#     """Test publication fails with missing metax ID."""
#
#     async def test_metax_publish_dataset_with_missing_metax_id(self, client_logged_in, database, submission_fega):
#         """Test publishing dataset to Metax service after submission failed to create Metax draft dataset.
#
#         Test will create study and dataset normally. After that imitating missing Metax connection will be done
#         with deleting object's metax ID and making call to mocked Metax service to remove Metax dataset from drafts.
#         Then objects will be published in metadata-submitter which should start a flow of creating draft dataset to
#         Metax and only then publishing it.
#
#         :param client_logged_in: HTTP client in which request call is made
#         :param submission_fega: id of the submission where objects reside
#         """
#         objects = []
#         for schema, filename in {
#             ("study", "SRP000539.xml"),
#             ("dataset", "dataset.xml"),
#         }:
#             accession_id, _ = await post_object(client_logged_in, schema, submission_fega, filename)
#             async with client_logged_in.get(f"{objects_url}/{schema}/{accession_id}") as resp:
#                 res = await resp.json()
#                 # metax_id = res["metaxIdentifier"]
#             objects.append([schema, accession_id])
#             await delete_objects_metax_id(client_logged_in, database, schema, accession_id, metax_id)
#             async with client_logged_in.get(f"{objects_url}/{schema}/{accession_id}") as resp:
#                 res = await resp.json()
#                 # assert res["metaxIdentifier"] == ""
#
#         # Add DOI and publish the submission
#         doi_data_raw = await create_request_json_data("doi", "test_doi.json")
#         await put_submission_doi(client_logged_in, submission_fega, doi_data_raw)
#         dac_data = await create_request_json_data("dac", "dac_rems.json")
#         await put_submission_dac(client_logged_in, submission_fega, dac_data)
#         await publish_submission(client_logged_in, submission_fega)
#
#         for schema, accession_id in objects:
#             async with client_logged_in.get(f"{objects_url}/{schema}/{accession_id}") as resp:
#                 assert resp.status == 200, f"HTTP Status code error, got {resp.status}"
#                 res = await resp.json()
#                 assert res["metaxIdentifier"] != ""
