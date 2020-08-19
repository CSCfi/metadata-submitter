"""
Run integration tests against backend api endpoints.

Deleting from db is currently not supported, objects added to db in different
should be taken into account.
"""

import asyncio
import logging
from pathlib import Path

import aiofiles
import aiohttp
from aiohttp import FormData

# === Global vars ===
FORMAT = (
    "[%(asctime)s][%(name)s][%(process)d %(processName)s]" "[%(levelname)-8s](L:%(lineno)s) %(funcName)s: %(message)s"
)
logging.basicConfig(format=FORMAT, datefmt="%Y-%m-%d %H:%M:%S")
LOG = logging.getLogger(__name__)
LOG.setLevel(logging.DEBUG)

testfiles_root = Path(__file__).parent.parent / "test_files"
test_xml_files = [
    ("study", "SRP000539.xml"),
    ("sample", "SRS001433.xml"),
    ("run", "ERR000076.xml"),
    ("experiment", "ERX000119.xml"),
    ("analysis", "ERZ266973.xml"),
]
test_json_files = [
    ("study", "SRP000539.json", "SRP000539.json"),
    ("sample", "SRS001433.json", "SRS001433.json"),
    ("run", "ERR000076.json", "ERR000076.json"),
    ("experiment", "ERX000119.json", "ERX000119.json"),
    ("analysis", "ERZ266973.json", "ERZ266973.json"),
]
base_url = "http://localhost:5430/objects"
drafts_url = "http://localhost:5430/drafts"
folders_url = "http://localhost:5430/folders"


# === Helper functions ===
async def create_request_data(schema, filename):
    """Create request data from pairs of schemas and filenames.

    :param schema: name of the schema (folder) used for testing
    :param filename: name of the file used for testing.
    """
    data = FormData()
    path_to_file = testfiles_root / schema / filename
    path = path_to_file.as_posix()
    async with aiofiles.open(path, mode="r") as f:
        data.add_field(schema.upper(), await f.read(), filename=filename, content_type="text/xml")
    return data


async def create_request_json_data(schema, filename):
    """Create request data from pairs of schemas and filenames.

    :param schema: name of the schema (folder) used for testing
    :param filename: name of the file used for testing.
    """
    path_to_file = testfiles_root / schema / filename
    path = path_to_file.as_posix()
    async with aiofiles.open(path, mode="r") as f:
        data = await f.read()
    return data


async def post_object(sess, schema, filename):
    """Post one metadata object within session, returns accessionId."""
    data = await create_request_data(schema, filename)
    async with sess.post(f"{base_url}/{schema}", data=data) as resp:
        LOG.debug(f"Adding new object to {schema}")
        assert resp.status == 201, "HTTP Status code error"
        ans = await resp.json()
        return ans["accessionId"]


async def delete_object(sess, schema, accession_id):
    """Delete metadata object within session."""
    async with sess.delete(f"{base_url}/{schema}/{accession_id}") as resp:
        LOG.debug(f"Deleting object {accession_id} from {schema}")
        assert resp.status == 204, "HTTP Status code error"


async def put_draft(sess, schema, filename, filename2):
    """Post & put one metadata object within session, returns accessionId."""
    data = await create_request_json_data(schema, filename)
    async with sess.post(f"{drafts_url}/{schema}", data=data) as resp:
        LOG.debug(f"Adding new object to {schema}")
        assert resp.status == 201, "HTTP Status code error"
        ans = await resp.json()
        test_id = ans["accessionId"]
    data2 = await create_request_json_data(schema, filename2)
    async with sess.put(f"{drafts_url}/{schema}/{test_id}", data=data2) as resp:
        LOG.debug(f"Replace object in {schema}")
        assert resp.status == 200, "HTTP Status code error"
        ans_put = await resp.json()
        assert ans_put["accessionId"] == test_id, "accession ID error"
        return ans_put["accessionId"]


async def patch_draft(sess, schema, filename, filename2):
    """Post & patch one metadata object within session, return accessionId."""
    data = await create_request_json_data(schema, filename)
    async with sess.post(f"{drafts_url}/{schema}", data=data) as resp:
        LOG.debug(f"Adding new object to {schema}")
        assert resp.status == 201, "HTTP Status code error"
        ans = await resp.json()
        test_id = ans["accessionId"]
    data = await create_request_json_data(schema, filename2)
    async with sess.patch(f"{drafts_url}/{schema}/{test_id}", data=data) as resp:
        LOG.debug(f"Update object in {schema}")
        assert resp.status == 200, "HTTP Status code error"
        ans_put = await resp.json()
        assert ans_put["accessionId"] == test_id, "accession ID error"
        return ans_put["accessionId"]


async def delete_draft(sess, schema, accession_id):
    """Delete metadata object within session."""
    async with sess.delete(f"{drafts_url}/{schema}/{accession_id}") as resp:
        LOG.debug(f"Deleting object {accession_id} from {schema}")
        assert resp.status == 204, "HTTP Status code error"


async def post_folder(sess, data):
    """Post one object folder within session, returns folderId."""
    async with sess.post(f"{folders_url}", data=data) as resp:
        LOG.debug("Adding new folder")
        assert resp.status == 201, "HTTP Status code error"
        ans = await resp.json()
        return ans["folderId"]


async def delete_folder(sess, folder_id):
    """Delete object folder within session."""
    async with sess.delete(f"{folders_url}/{folder_id}") as resp:
        LOG.debug(f"Deleting folder {folder_id}")
        assert resp.status == 204, "HTTP Status code error"


# === Integration tests ===
async def test_crud_works(schema, filename):
    """Test REST api POST, GET and DELETE reqs.

    Tries to create new object, gets accession id and checks if correct
    resource is returned with that id. Finally deletes the object and checks it
    was deleted.

    :param schema: name of the schema (folder) used for testing
    :param filename: name of the file used for testing.
    """
    async with aiohttp.ClientSession() as sess:
        accession_id = await post_object(sess, schema, filename)
        async with sess.get(f"{base_url}/{schema}/{accession_id}") as resp:
            LOG.debug(f"Checking that {accession_id} JSON is in {schema}")
            assert resp.status == 200, "HTTP Status code error"
        async with sess.get(f"{base_url}/{schema}/{accession_id}" "?format=xml") as resp:
            LOG.debug(f"Checking that {accession_id} XML is in {schema}")
            assert resp.status == 200, "HTTP Status code error"

        await delete_object(sess, schema, accession_id)
        async with sess.get(f"{base_url}/{schema}/{accession_id}") as resp:
            LOG.debug(f"Checking that JSON object {accession_id} was deleted")
            assert resp.status == 404, "HTTP Status code error"
        async with sess.get(f"{base_url}/{schema}/{accession_id}" "?format=xml") as resp:
            LOG.debug(f"Checking that XML object {accession_id} was deleted")
            assert resp.status == 404, "HTTP Status code error"


async def test_crud_drafts_works(schema, filename, filename2):
    """Test drafts REST api POST, PUT and DELETE reqs.

    Tries to create new draft object, gets accession id and checks if correct
    resource is returned with that id. Finally deletes the object and checks it
    was deleted.

    :param schema: name of the schema (folder) used for testing
    :param filename: name of the file used for testing.
    """
    async with aiohttp.ClientSession() as sess:
        accession_id = await put_draft(sess, schema, filename, filename2)
        async with sess.get(f"{drafts_url}/{schema}/{accession_id}") as resp:
            LOG.debug(f"Checking that {accession_id} JSON is in {schema}")
            assert resp.status == 200, "HTTP Status code error"

        await delete_draft(sess, schema, accession_id)
        async with sess.get(f"{drafts_url}/{schema}/{accession_id}") as resp:
            LOG.debug(f"Checking that JSON object {accession_id} was deleted")
            assert resp.status == 404, "HTTP Status code error"


async def test_put_drafts_works(schema, filename, filename2):
    """Test REST api POST, PUT and DELETE reqs.

    Tries to create put and patch object, gets accession id and
    checks if correct resource is returned with that id.
    Finally deletes the object and checks it was deleted.

    :param schema: name of the schema (folder) used for testing
    :param filename: name of the file used for testing.
    """
    async with aiohttp.ClientSession() as sess:
        accession_id = await put_draft(sess, schema, filename, filename2)
        async with sess.get(f"{drafts_url}/{schema}/{accession_id}") as resp:
            LOG.debug(f"Checking that {accession_id} JSON is in {schema}")
            assert resp.status == 200, "HTTP Status code error"

        await delete_draft(sess, schema, accession_id)
        async with sess.get(f"{drafts_url}/{schema}/{accession_id}") as resp:
            LOG.debug(f"Checking that JSON object {accession_id} was deleted")
            assert resp.status == 404, "HTTP Status code error"


async def test_patch_drafts_works(schema, filename, filename2):
    """Test REST api POST, PATCH and DELETE reqs.

    Tries to create put and patch object, gets accession id and
    checks if correct resource is returned with that id.
    Finally deletes the object and checks it was deleted.

    :param schema: name of the schema (folder) used for testing
    :param filename: name of the file used for testing.
    """
    async with aiohttp.ClientSession() as sess:
        accession_id = await patch_draft(sess, schema, filename, filename2)
        async with sess.get(f"{drafts_url}/{schema}/{accession_id}") as resp:
            LOG.debug(f"Checking that {accession_id} JSON is in {schema}")
            res = await resp.json()
            assert res["centerName"] == "GEOM", "content mismatch"
            assert res["alias"] == "GSE10968", "content mismatch"
            assert resp.status == 200, "HTTP Status code error"

        await delete_draft(sess, schema, accession_id)
        async with sess.get(f"{drafts_url}/{schema}/{accession_id}") as resp:
            LOG.debug(f"Checking that JSON object {accession_id} was deleted")
            assert resp.status == 404, "HTTP Status code error"


async def test_querying_works():
    """Test query endpoint with working and failing query."""
    async with aiohttp.ClientSession() as sess:

        accession_ids = await asyncio.gather(
            *[post_object(sess, schema, filename) for schema, filename in test_xml_files]
        )

        queries = {
            "study": [
                ("studyTitle", "integrated"),
                ("studyType", "Other"),
                ("studyAbstract", "arabidopsis thaliana"),
                ("studyAttributes", "prjna107265"),
                ("studyAttributes", "parent_bioproject"),
            ],
            "sample": [
                ("title", "HapMap sample"),
                ("description", "human hapmap individual"),
                ("centerName", "hapmap"),
                ("sampleName", "homo sapiens"),
                ("scientificName", "homo sapiens"),
                ("sampleName", 9606),
            ],
            "run": [
                ("fileType", "srf"),
                ("experimentReference", "g1k-bgi-na18542"),
                ("experimentReference", "erx000037"),
            ],
            "experiment": [("studyReference", "1000Genomes project pilot")],
            "analysis": [
                ("fileType", "other"),
                ("studyReference", "HipSci___RNAseq___"),
                ("sampleReference", "HPSI0114i-eipl_3"),
            ],
        }

        async def do_one_query(schema, key, value, expected_status):
            async with sess.get(f"{base_url}/{schema}?{key}={value}") as resp:
                assert resp.status == expected_status, "HTTP Status code error"

        for schema, schema_queries in queries.items():
            LOG.debug(f"Querying {schema} collection with working params")
            await asyncio.gather(*[do_one_query(schema, key, value, 200) for key, value in schema_queries])
            LOG.debug("Querying {schema} collection with non-working params")
            invalid = "yoloswaggings"
            await asyncio.gather(*[do_one_query(schema, key, invalid, 404) for key, _ in schema_queries])

        await asyncio.gather(
            *[
                delete_object(sess, schema, accession_id)
                for schema, accession_id in list(zip([schema for schema, _ in test_xml_files], accession_ids))
            ]
        )


async def test_getting_all_objects_from_schema_works():
    """Check that /objects/study returns objects with correct pagination."""
    async with aiohttp.ClientSession() as sess:

        # Add objects
        accession_ids = await asyncio.gather(*[post_object(sess, "study", "SRP000539.xml") for _ in range(13)])

        # Test default values
        async with sess.get(f"{base_url}/study") as resp:
            assert resp.status == 200
            ans = await resp.json()
            assert ans["page"]["page"] == 1
            assert ans["page"]["size"] == 10
            assert ans["page"]["totalPages"] == 2
            assert ans["page"]["totalObjects"] == 13
            assert len(ans["objects"]) == 10

        # Test with custom pagination values
        async with sess.get(f"{base_url}/study?page=2&per_page=3") as resp:
            assert resp.status == 200
            ans = await resp.json()
            assert ans["page"]["page"] == 2
            assert ans["page"]["size"] == 3
            assert ans["page"]["totalPages"] == 5
            assert ans["page"]["totalObjects"] == 13
            assert len(ans["objects"]) == 3

        # Test with wrong pagination values
        async with sess.get(f"{base_url}/study?page=-1") as resp:
            assert resp.status == 400
        async with sess.get(f"{base_url}/study?per_page=0") as resp:
            assert resp.status == 400

        # Delete objects
        await asyncio.gather(*[delete_object(sess, "study", accession_id) for accession_id in accession_ids])


async def test_crud_folders_works():
    """Test folders REST api POST, GET and DELETE reqs.

    Tries to create new folder, gets folder id and checks if correct resource is returned with that id.
    Finally deletes the folder and checks it was deleted.
    """
    async with aiohttp.ClientSession() as sess:
        data = {"name": "test", "description": "test folder"}
        folder_id = await post_object(sess, data)
        async with sess.get(f"{folders_url}/{folder_id}") as resp:
            LOG.debug(f"Checking that folder {folder_id} was created")
            assert resp.status == 200, "HTTP Status code error"

        await delete_object(sess, folder_id)
        async with sess.get(f"{folders_url}/{folder_id}") as resp:
            LOG.debug(f"Checking that folder {folder_id} was deleted")
            assert resp.status == 404, "HTTP Status code error"


async def test_patch_folders_works():
    """Test folders REST api PATCH reqs.

    Tries to patch a folder with a JSON patch in the request, gets folder id and
    checks if correct resource is returned with that id.
    """
    raise NotImplementedError


async def test_crud_users_works():
    """Test users REST api GET and DELETE reqs.

    Tries to create new user, gets user id and checks if correct resource is returned with that id.
    Finally deletes the user and checks it was deleted.
    """
    raise NotImplementedError


async def test_patch_users_works():
    """Test users REST api PATCH reqs.

    Tries to patch an user with a JSON patch in the request, gets user id and
    checks if correct resource is returned with that id.
    """
    raise NotImplementedError


async def main():
    """Launch different test tasks and run them."""
    # Test adding and getting objects
    LOG.debug("=== Testing basic CRUD operations ===")
    await asyncio.gather(*[test_crud_works(schema, file) for schema, file in test_xml_files])

    # Test adding and getting draft objects
    LOG.debug("=== Testing basic CRUD drafts operations ===")
    await asyncio.gather(*[test_crud_drafts_works(schema, file, file2) for schema, file, file2 in test_json_files])

    # Test patch and put
    LOG.debug("=== Testing patch and put drafts operations ===")
    await test_put_drafts_works("sample", "SRS001433.json", "put.json")
    await test_patch_drafts_works("study", "SRP000539.json", "patch.json")

    # Test queries
    LOG.debug("=== Testing queries ===")
    await test_querying_works()

    # Test /objects/study endpoint for query pagination
    LOG.debug("=== Testing getting all objects & pagination ===")
    await test_getting_all_objects_from_schema_works()

    # Test adding and getting folders
    LOG.debug("=== Testing basic CRUD folder operations ===")
    await test_crud_folders_works()


if __name__ == "__main__":
    asyncio.run(main())
