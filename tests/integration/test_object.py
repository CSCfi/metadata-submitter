"""Test object manipulations."""

import logging
from typing import Any

import defusedxml.ElementTree as ET

from tests.integration.conf import objects_url, test_bigpicture_xml_files, test_fega_xml_files
from tests.integration.helpers import (
    check_object_exists,
    delete_object,
    post_multi_object,
    post_object,
    put_object,
)

LOG = logging.getLogger(__name__)
LOG.setLevel(logging.DEBUG)


class TestObjects:
    """Test adding and getting objects with XML files."""

    async def test_crud_works_fega_and_bp_xml(self, client_logged_in, submission_factory):
        """Test REST API POST, GET and DELETE reqs.

        Tries to create new object, gets accession id and checks if correct
        resource is returned with that id. Finally deletes the object and checks it
        was deleted.

        :param client_logged_in: HTTP client user
        :param submission_factory: The factory that creates and deletes submissions
        """
        fega_submission_id, _ = await submission_factory("FEGA")
        bp_submission_id, _ = await submission_factory("Bigpicture")

        async def assert_crud_works(schema, filename, submission_id):
            """Individual tests to be run in parallel."""
            accession_id = await post_object(client_logged_in, schema, submission_id, filename)
            async with client_logged_in.get(f"{objects_url}/{schema}/{accession_id}") as resp:
                LOG.debug("Checking that %s JSON is in %s", accession_id, schema)
                res = await resp.json()
                assert resp.status == 200, f"HTTP Status code error, got {resp.status}: {res}"
            await check_object_exists(client_logged_in, schema, accession_id)
            async with client_logged_in.get(f"{objects_url}/{schema}/{accession_id}?format=xml") as resp:
                LOG.debug("Checking that %s XML is in %s", accession_id, schema)
                assert resp.status == 200, f"HTTP Status code error, got {resp.status}"

            await delete_object(client_logged_in, schema, accession_id)
            async with client_logged_in.get(f"{objects_url}/{schema}/{accession_id}") as resp:
                LOG.debug("Checking that JSON object %s was deleted", accession_id)
                assert resp.status == 404, f"HTTP Status code error, got {resp.status}"
            async with client_logged_in.get(f"{objects_url}/{schema}/{accession_id}?format=xml") as resp:
                LOG.debug("Checking that XML object %s was deleted", accession_id)
                assert resp.status == 404, f"HTTP Status code error, got {resp.status}"

        for schema, filename in test_fega_xml_files:
            await assert_crud_works(schema, filename, fega_submission_id)
        for schema, filename in test_bigpicture_xml_files:
            await assert_crud_works(schema, filename, bp_submission_id)

    async def test_crud_with_multi_xml(self, client_logged_in, submission_factory):
        """Test CRUD for a submitted XML file with multiple metadata objects.

        Tries to create new objects, gets accession ids and checks if correct
        resource is returned with those ids. Finally deletes the objects and checks it
        was deleted.

        :param client_logged_in: HTTP client in which request call is made
        :param submission_factory: The factory that creates and deletes submissions
        """

        fega_submission_id, _ = await submission_factory("FEGA")
        bp_submission_id, _ = await submission_factory("Bigpicture")

        metadata_objects: list[dict[str, Any]] = []

        async def assert_metadata_objects(_accession_ids, _schema):
            for _accession_id in _accession_ids:
                metadata_objects.append({"schema": _schema, "id": _accession_id})
                async with client_logged_in.get(f"{objects_url}/{_schema}/{_accession_id}") as resp:
                    LOG.debug("Checking that %s JSON is in %s", _accession_id, _schema)
                    assert resp.status == 200, f"HTTP Status code error, got {resp.status}"
                async with client_logged_in.get(f"{objects_url}/{_schema}/{_accession_id}?format=xml") as resp:
                    LOG.debug("Checking that %s XML is in %s", _accession_id, _schema)
                    assert resp.status == 200, f"HTTP Status code error, got {resp.status}"
                    # Also check the stored XML contents were modified to match the json object
                    # and only include a single child item
                    reformatted_xml = await resp.text()
                    root = ET.fromstring(reformatted_xml)
                    child_elements = list(root)
                    assert len(child_elements) == 1, "Wrong number of child elements found"
                    tags = [
                        "POLICY",
                        "IMAGE",
                        "BIOLOGICAL_BEING",
                        "CASE",
                        "SPECIMEN",
                        "SLIDE",
                        "BLOCK",
                        "STAINING",
                        "OBSERVER",
                    ]
                    assert child_elements[0].tag in tags, "Wrong child element was found"

        schema = "policy"
        filename = "policy2.xml"
        accession_ids = await post_multi_object(client_logged_in, schema, fega_submission_id, filename)
        await assert_metadata_objects(accession_ids, schema)

        schema = "bpimage"
        filename = "images_multi.xml"
        accession_ids = await post_multi_object(client_logged_in, schema, bp_submission_id, filename)
        await assert_metadata_objects(accession_ids, schema)

        schema = "bpsample"
        filename = "samples.xml"
        accession_ids = await post_multi_object(client_logged_in, schema, bp_submission_id, filename)
        await assert_metadata_objects(accession_ids, schema)

        schema = "bpstaining"
        filename = "stainings.xml"
        accession_ids = await post_multi_object(client_logged_in, schema, bp_submission_id, filename)
        await assert_metadata_objects(accession_ids, schema)

        schema = "bpobserver"
        filename = "observers.xml"
        accession_ids = await post_multi_object(client_logged_in, schema, bp_submission_id, filename)
        await assert_metadata_objects(accession_ids, schema)

        assert len(metadata_objects) == 21, "Wrong amount of items were added during previous requests."
        for metadata_object in metadata_objects:
            _schema = metadata_object["schema"]
            _id = metadata_object["id"]
            await delete_object(client_logged_in, _schema, _id)
            async with client_logged_in.get(f"{objects_url}/{_schema}/{_id}") as resp:
                LOG.debug("Checking that JSON object %s was deleted", _id)
                assert resp.status == 404, f"HTTP Status code error, got {resp.status}"
            async with client_logged_in.get(f"{objects_url}/{_schema}/{_id}?format=xml") as resp:
                LOG.debug("Checking that XML object %s was deleted", _id)
                assert resp.status == 404, f"HTTP Status code error, got {resp.status}"


class TestObjectsJsonXml:
    """Test creating objects with XML and CSV files."""

    async def test_put_objects(self, client_logged_in, submission_factory):
        """Test PUT reqs.

        Tries to create new object, gets accession id and checks if correct
        resource is returned with that id. Try to use PUT with JSON and expect failure,
        try to use PUT with XML and expect success.

        :param client_logged_in: HTTP client in which request call is made
        :param submission_factory: The factory that creates and deletes submissions
        """
        submission_id, _ = await submission_factory("FEGA")

        accession_id = await post_object(client_logged_in, "study", submission_id, "SRP000539.xml")
        await put_object(client_logged_in, "study", accession_id, "SRP000539.json")
        await put_object(client_logged_in, "study", accession_id, "SRP000539_put.xml")
        await check_object_exists(client_logged_in, "study", accession_id)
        await delete_object(client_logged_in, "study", accession_id)
