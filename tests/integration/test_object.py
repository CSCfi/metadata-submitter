"""Test object manipulations."""
import asyncio
import logging

from tests.integration.conf import (
    objects_url,
    submissions_url,
    test_bigpicture_xml_files,
    test_fega_xml_files,
)
from tests.integration.helpers import (
    check_submissions_object_patch,
    delete_object,
    post_multi_object,
    post_object,
    post_object_expect_status,
    put_object_json,
    put_object_xml,
)

LOG = logging.getLogger(__name__)
LOG.setLevel(logging.DEBUG)


class TestObjects:
    """Test adding and getting objects with XML and CSV files."""

    async def test_crud_works(self, client_logged_in, submission_fega, submission_bigpicture):
        """Test REST API POST, GET and DELETE reqs.

        Tries to create new object, gets accession id and checks if correct
        resource is returned with that id. Finally deletes the object and checks it
        was deleted.

        :param client_logged_in: HTTP client_logged_in_logged_inion in which request call is made
        :param schema: name of the schema (submission) used for testing
        :param filename: name of the file used for testing
        :param submission_fega: id of the submission used to group fega submission
        :param submission_bigpicture: id of submission used to group BP submission
        """

        async def crud_works(schema, filename, submission_id):
            """Individual tests to be run in parallel."""
            accession_id = await post_object(client_logged_in, schema, submission_id, filename)
            async with client_logged_in.get(f"{objects_url}/{schema}/{accession_id[0]}") as resp:
                LOG.debug(f"Checking that {accession_id[0]} JSON is in {schema}")
                res = await resp.json()
                assert resp.status == 200, f"HTTP Status code error, got {resp.status}: {res}"
                title = res["descriptor"].get("studyTitle", "") if schema == "study" else res.get("title", "")
            await check_submissions_object_patch(
                client_logged_in,
                submission_id,
                schema,
                accession_id[0],
                title,
                filename,
            )
            async with client_logged_in.get(f"{objects_url}/{schema}/{accession_id[0]}?format=xml") as resp:
                LOG.debug(f"Checking that {accession_id[0]} XML is in {schema}")
                assert resp.status == 200, f"HTTP Status code error, got {resp.status}"

            await delete_object(client_logged_in, schema, accession_id[0])
            async with client_logged_in.get(f"{objects_url}/{schema}/{accession_id[0]}") as resp:
                LOG.debug(f"Checking that JSON object {accession_id[0]} was deleted")
                assert resp.status == 404, f"HTTP Status code error, got {resp.status}"
            async with client_logged_in.get(f"{objects_url}/{schema}/{accession_id[0]}?format=xml") as resp:
                LOG.debug(f"Checking that XML object {accession_id[0]} was deleted")
                assert resp.status == 404, f"HTTP Status code error, got {resp.status}"

            async with client_logged_in.get(f"{submissions_url}/{submission_id}") as resp:
                LOG.debug(f"Checking that object {accession_id[0]} was deleted from submission {submission_id}")
                res = await resp.json()
                expected_true = not any(d["accessionId"] == accession_id[0] for d in res["metadataObjects"])
                assert expected_true, f"object {accession_id[0]} still exists"

        gather_items = []
        for schema, filename in test_fega_xml_files:
            gather_items.append(crud_works(schema, filename, submission_fega))
        for schema, filename in test_bigpicture_xml_files:
            gather_items.append(crud_works(schema, filename, submission_bigpicture))
        # Run in parallel to test concurrent uploads
        await asyncio.gather(*gather_items)

    async def test_crud_with_multi_xml(self, client_logged_in, submission_fega, submission_bigpicture):
        """Test CRUD for a submitted XML file with multiple metadata objects.

        Tries to create new objects, gets accession ids and checks if correct
        resource is returned with those ids. Finally deletes the objects and checks it
        was deleted.

        :param client_logged_in: HTTP client in which request call is made
        :param submission_fega: id of the submission used to group fega submission
        :param submission_bigpicture: id of submission used to group BP submission
        """
        items = []

        async def test_query(data, schema):
            for item in data:
                items.append(item)
                async with client_logged_in.get(f"{objects_url}/{schema}/{item['accessionId']}") as resp:
                    LOG.debug(f"Checking that {item['accessionId']} JSON is in {schema}")
                    assert resp.status == 200, f"HTTP Status code error, got {resp.status}"
                async with client_logged_in.get(f"{objects_url}/{schema}/{item['accessionId']}?format=xml") as resp:
                    LOG.debug(f"Checking that {item['accessionId']} XML is in {schema}")
                    assert resp.status == 200, f"HTTP Status code error, got {resp.status}"

        _schema = "policy"
        _filename = "policy2.xml"
        data = await post_multi_object(client_logged_in, _schema, submission_fega, _filename)
        await test_query(data, _schema)

        _schema = "bpimage"
        _filename = "images_multi.xml"
        data = await post_multi_object(client_logged_in, _schema, submission_bigpicture, _filename)
        await test_query(data, _schema)

        _schema = "bpsample"
        _filename = "template_samples.xml"
        data = await post_multi_object(client_logged_in, _schema, submission_bigpicture, _filename)
        await test_query(data, _schema)

        _schema = "bpstaining"
        _filename = "stainings.xml"
        data = await post_multi_object(client_logged_in, _schema, submission_bigpicture, _filename)
        await test_query(data, _schema)

        assert len(items) == 18, "Wrong amount of items were added during previous requests."
        for item in items:
            _id, _schema = item["accessionId"], item["schema"]
            await delete_object(client_logged_in, _schema, _id)
            async with client_logged_in.get(f"{objects_url}/{_schema}/{_id}") as resp:
                LOG.debug(f"Checking that JSON object {_id} was deleted")
                assert resp.status == 404, f"HTTP Status code error, got {resp.status}"
            async with client_logged_in.get(f"{objects_url}/{_schema}/{_id}?format=xml") as resp:
                LOG.debug(f"Checking that XML object {_id} was deleted")
                assert resp.status == 404, f"HTTP Status code error, got {resp.status}"

    async def test_csv(self, client_logged_in, submission_fega):
        """Test CRUD for a submitted CSV file.

        Test tries with good csv file first for sample object, after which we try with empty file.
        After this we try with study object which is not allowed.

        :param client_logged_in: HTTP client in which request call is made
        :param submission_fega: id of the submission used to group submission
        """
        _schema = "sample"
        _filename = "EGAformat.csv"
        samples = await post_object(client_logged_in, _schema, submission_fega, _filename)
        # there are 3 rows and we expected to get 3rd
        assert len(samples[0]) == 3, f"expected nb of CSV entries does not match, we got: {len(samples[0])}"
        # _first_csv_row_id = accession_id[0][0]["accessionId"]
        first_sample = samples[0][0]["accessionId"]

        async with client_logged_in.get(f"{objects_url}/{_schema}/{first_sample}") as resp:
            LOG.debug(f"Checking that {first_sample} JSON is in {_schema}")
            assert resp.status == 200, f"HTTP Status code error, got {resp.status}"
            res = await resp.json()
            title = res.get("title", "")
        await check_submissions_object_patch(client_logged_in, submission_fega, _schema, samples, title, _filename)

        await delete_object(client_logged_in, _schema, first_sample)
        async with client_logged_in.get(f"{objects_url}/{_schema}/{first_sample}") as resp:
            LOG.debug(f"Checking that JSON object {first_sample} was deleted")
            assert resp.status == 404, f"HTTP Status code error, got {resp.status}"

        async with client_logged_in.get(f"{submissions_url}/{submission_fega}") as resp:
            LOG.debug(f"Checking that object {first_sample} was deleted from submission {submission_fega}")
            res = await resp.json()
            expected_true = not any(d["accessionId"] == first_sample for d in res["metadataObjects"])
            assert expected_true, f"object {first_sample} still exists"

        _filename = "empty.csv"
        # status should be 400
        await post_object_expect_status(client_logged_in, _schema, submission_fega, _filename, 400)

        _filename = "EGA_sample_w_issue.csv"
        # status should be 201 but we expect 3 rows, as the CSV has 4 rows one of which is empty
        samples_2 = await post_object_expect_status(client_logged_in, _schema, submission_fega, _filename, 201)
        assert len(samples_2[0]) == 3, f"expected nb of CSV entries does not match, we got: {len(samples_2[0])}"

        for sample in samples_2[0] + samples[0][1:]:
            await delete_object(client_logged_in, _schema, sample["accessionId"])


class TestObjectsJsonXml:
    """Test creating objects with XML and CSV files."""

    async def test_put_objects(self, client_logged_in, submission_fega):
        """Test PUT reqs.

        Tries to create new object, gets accession id and checks if correct
        resource is returned with that id. Try to use PUT with JSON and expect failure,
        try to use PUT with XML and expect success.

        :param client_logged_in: HTTP client in which request call is made
        :param submission_fega: id of the submission used to group submission
        """
        accession_id = await post_object(client_logged_in, "study", submission_fega, "SRP000539.xml")
        await put_object_json(client_logged_in, "study", accession_id[0], "SRP000539.json")
        await put_object_xml(client_logged_in, "study", accession_id[0], "SRP000539_put.xml")
        await check_submissions_object_patch(
            client_logged_in,
            submission_fega,
            "study",
            accession_id,
            "Highly integrated epigenome maps in Arabidopsis - whole genome shotgun bisulfite sequencing",
            "SRP000539_put.xml",
        )
        await delete_object(client_logged_in, "study", accession_id[0])
