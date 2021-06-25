"""
Run integration tests against backend api endpoints.

Deleting from db is currently not supported, objects added to db in different
should be taken into account.
"""

import asyncio
import json
import logging
from pathlib import Path
import urllib
import xml.etree.ElementTree as ET

import aiofiles
import aiohttp
from aiohttp import FormData

# === Global vars ===
FORMAT = "[%(asctime)s][%(name)s][%(process)d %(processName)s][%(levelname)-8s](L:%(lineno)s) %(funcName)s: %(message)s"
logging.basicConfig(format=FORMAT, datefmt="%Y-%m-%d %H:%M:%S")
LOG = logging.getLogger(__name__)
LOG.setLevel(logging.DEBUG)

testfiles_root = Path(__file__).parent.parent / "test_files"
test_xml_files = [
    ("study", "SRP000539.xml"),
    ("sample", "SRS001433.xml"),
    ("run", "ERR000076.xml"),
    ("experiment", "ERX000119.xml"),
    ("experiment", "paired.xml"),
    ("experiment", "sample_description.xml"),
    ("analysis", "ERZ266973.xml"),
    ("analysis", "processed_reads_analysis.xml"),
    ("analysis", "reference_alignment_analysis.xml"),
    ("analysis", "reference_sequence_analysis.xml"),
    ("analysis", "sequence_assembly_analysis.xml"),
    ("analysis", "sequence_variation_analysis.xml"),
    ("dac", "dac.xml"),
    ("policy", "policy.xml"),
    ("dataset", "dataset.xml"),
]
test_json_files = [
    ("study", "SRP000539.json", "SRP000539.json"),
    ("sample", "SRS001433.json", "SRS001433.json"),
    ("run", "ERR000076.json", "ERR000076.json"),
    ("experiment", "ERX000119.json", "ERX000119.json"),
    ("analysis", "ERZ266973.json", "ERZ266973.json"),
]
base_url = "http://localhost:5430"
mock_auth_url = "http://localhost:8000"
objects_url = f"{base_url}/objects"
drafts_url = f"{base_url}/drafts"
folders_url = f"{base_url}/folders"
users_url = f"{base_url}/users"
submit_url = f"{base_url}/submit"
publish_url = f"{base_url}/publish"

user_id = "current"
test_user_given = "Given"
test_user_family = "Family"
test_user = "user_given@test.what"

other_test_user_given = "Mock"
other_test_user_family = "Family"
other_test_user = "mock_user@test.what"


# === Helper functions ===
async def login(sess, eppn, given, family):
    """Mock login."""
    params = {
        "eppn": eppn,
        "family": family,
        "given": given,
    }

    # Prepare response
    url = f"{mock_auth_url}/setmock?{urllib.parse.urlencode(params)}"
    async with sess.get(f"{url}"):
        LOG.debug("Setting mock user")
    async with sess.get(f"{base_url}/aai"):
        LOG.debug("Doing mock user login")


async def create_request_data(schema, filename):
    """Create request data from pairs of schemas and filenames.

    :param schema: name of the schema (folder) used for testing
    :param filename: name of the file used for testing.
    """
    request_data = FormData()
    path_to_file = testfiles_root / schema / filename
    path = path_to_file.as_posix()
    async with aiofiles.open(path, mode="r") as f:
        request_data.add_field(schema.upper(), await f.read(), filename=filename, content_type="text/xml")
    return request_data


async def create_multi_file_request_data(filepairs):
    """Create request data with multiple files.

    :param filepairs: tuple containing pairs of schemas and filenames used for testing
    """
    request_data = FormData()
    for schema, filename in filepairs:
        path_to_file = testfiles_root / schema / filename
        path = path_to_file.as_posix()
        async with aiofiles.open(path, mode="r") as f:
            request_data.add_field(schema.upper(), await f.read(), filename=filename, content_type="text/xml")
    return request_data


async def create_request_json_data(schema, filename):
    """Create request data from pairs of schemas and filenames.

    :param schema: name of the schema (folder) used for testing
    :param filename: name of the file used for testing.
    """
    path_to_file = testfiles_root / schema / filename
    path = path_to_file.as_posix()
    async with aiofiles.open(path, mode="r") as f:
        request_data = await f.read()
    return request_data


async def post_object(sess, schema, filename):
    """Post one metadata object within session, returns accessionId.

    :param sess: HTTP session in which request call is made
    :param schema: name of the schema (folder) used for testing
    :param filename: name of the file used for testing.
    """
    request_data = await create_request_data(schema, filename)
    async with sess.post(f"{objects_url}/{schema}", data=request_data) as resp:
        LOG.debug(f"Adding new object to {schema}, via XML file {filename}")
        assert resp.status == 201, "HTTP Status code error"
        ans = await resp.json()
        return ans["accessionId"], schema


async def post_object_json(sess, schema, filename):
    """Post & put one metadata object within session, returns accessionId.

    :param sess: HTTP session in which request call is made
    :param schema: name of the schema (folder) used for testing
    :param filename: name of the file used for testing.
    """
    request_data = await create_request_json_data(schema, filename)
    async with sess.post(f"{objects_url}/{schema}", data=request_data) as resp:
        LOG.debug(f"Adding new object to {schema}, via JSON file {filename}")
        assert resp.status == 201, "HTTP Status code error"
        ans = await resp.json()
        return ans["accessionId"]


async def delete_object(sess, schema, accession_id):
    """Delete metadata object within session.

    :param sess: HTTP session in which request call is made
    :param schema: name of the schema (folder) used for testing
    :param accession_id: id of the object
    """
    async with sess.delete(f"{objects_url}/{schema}/{accession_id}") as resp:
        LOG.debug(f"Deleting object {accession_id} from {schema}")
        assert resp.status == 204, "HTTP Status code error"


async def post_draft(sess, schema, filename):
    """Post one draft metadata object within session, returns accessionId.

    :param sess: HTTP session in which request call is made
    :param schema: name of the schema (folder) used for testing
    :param filename: name of the file used for testing.
    """
    request_data = await create_request_data(schema, filename)
    async with sess.post(f"{drafts_url}/{schema}", data=request_data) as resp:
        LOG.debug(f"Adding new draft object to {schema}, via XML file {filename}")
        assert resp.status == 201, "HTTP Status code error"
        ans = await resp.json()
        return ans["accessionId"]


async def post_draft_json(sess, schema, filename):
    """Post & put one metadata object within session, returns accessionId.

    :param sess: HTTP session in which request call is made
    :param schema: name of the schema (folder) used for testing
    :param filename: name of the file used for testing.
    """
    request_data = await create_request_json_data(schema, filename)
    async with sess.post(f"{drafts_url}/{schema}", data=request_data) as resp:
        LOG.debug(f"Adding new draft object to {schema}, via JSON file {filename}")
        assert resp.status == 201, "HTTP Status code error"
        ans = await resp.json()
        return ans["accessionId"]


async def get_draft(sess, schema, draft_id):
    """Get and return a drafted metadata object.

    :param sess: HTTP session in which request call is made
    :param schema: name of the schema (folder) used for testing
    :param draft_id: id of the draft
    """
    async with sess.get(f"{drafts_url}/{schema}/{draft_id}") as resp:
        LOG.debug(f"Checking that {draft_id} JSON exists")
        assert resp.status == 200, "HTTP Status code error"
        ans = await resp.json()
        return json.dumps(ans)


async def put_draft(sess, schema, draft_id, update_filename):
    """Put one metadata object within session, returns accessionId.

    :param sess: HTTP session in which request call is made
    :param schema: name of the schema (folder) used for testing
    :param draft_id: id of the draft
    :param update_filename: name of the file used to use for updating data.
    """
    request_data = await create_request_json_data(schema, update_filename)
    async with sess.put(f"{drafts_url}/{schema}/{draft_id}", data=request_data) as resp:
        LOG.debug(f"Replace draft object in {schema}")
        assert resp.status == 200, "HTTP Status code error"
        ans_put = await resp.json()
        assert ans_put["accessionId"] == draft_id, "accession ID error"
        return ans_put["accessionId"]


async def put_object_json(sess, schema, accession_id, update_filename):
    """Put one metadata object within session, returns accessionId.

    :param sess: HTTP session in which request call is made
    :param schema: name of the schema (folder) used for testing
    :param draft_id: id of the draft
    :param update_filename: name of the file used to use for updating data.
    """
    request_data = await create_request_json_data(schema, update_filename)
    async with sess.put(f"{objects_url}/{schema}/{accession_id}", data=request_data) as resp:
        LOG.debug(f"Try to replace object in {schema}")
        assert resp.status == 415, "HTTP Status code error"


async def put_object_xml(sess, schema, accession_id, update_filename):
    """Put one metadata object within session, returns accessionId.

    :param sess: HTTP session in which request call is made
    :param schema: name of the schema (folder) used for testing
    :param draft_id: id of the draft
    :param update_filename: name of the file used to use for updating data.
    """
    request_data = await create_request_data(schema, update_filename)
    async with sess.put(f"{objects_url}/{schema}/{accession_id}", data=request_data) as resp:
        LOG.debug(f"Replace object with XML data in {schema}")
        assert resp.status == 200, "HTTP Status code error"
        ans_put = await resp.json()
        assert ans_put["accessionId"] == accession_id, "accession ID error"
        return ans_put["accessionId"]


async def patch_draft(sess, schema, draft_id, update_filename):
    """Patch one metadata object within session, return accessionId.

    :param sess: HTTP session in which request call is made
    :param schema: name of the schema (folder) used for testing
    :param draft_id: id of the draft
    :param update_filename: name of the file used to use for updating data.
    """
    request_data = await create_request_json_data(schema, update_filename)
    async with sess.patch(f"{drafts_url}/{schema}/{draft_id}", data=request_data) as resp:
        LOG.debug(f"Update draft object in {schema}")
        assert resp.status == 200, "HTTP Status code error"
        ans_put = await resp.json()
        assert ans_put["accessionId"] == draft_id, "accession ID error"
        return ans_put["accessionId"]


async def delete_draft(sess, schema, draft_id):
    """Delete metadata object within session.

    :param sess: HTTP session in which request call is made
    :param schema: name of the schema (folder) used for testing
    :param draft_id: id of the draft
    """
    async with sess.delete(f"{drafts_url}/{schema}/{draft_id}") as resp:
        LOG.debug(f"Deleting draft object {draft_id} from {schema}")
        assert resp.status == 204, "HTTP Status code error"


async def post_folder(sess, data):
    """Post one object folder within session, returns folderId.

    :param sess: HTTP session in which request call is made
    :param data: data used to update the folder
    """
    async with sess.post(f"{folders_url}", data=json.dumps(data)) as resp:
        LOG.debug("Adding new folder")
        assert resp.status == 201, "HTTP Status code error"
        ans = await resp.json()
        return ans["folderId"]


async def patch_folder(sess, folder_id, json_patch):
    """Patch one object folder within session, return folderId.

    :param sess: HTTP session in which request call is made
    :param folder_id: id of the folder
    :param json_patch: JSON Patch object to use in PATCH call
    """
    async with sess.patch(f"{folders_url}/{folder_id}", data=json.dumps(json_patch)) as resp:
        LOG.debug(f"Updating folder {folder_id}")
        assert resp.status == 200, "HTTP Status code error"
        ans_patch = await resp.json()
        assert ans_patch["folderId"] == folder_id, "folder ID error"
        return ans_patch["folderId"]


async def publish_folder(sess, folder_id):
    """Publish one object folder within session, return folderId.

    :param sess: HTTP session in which request call is made
    :param folder_id: id of the folder
    """
    async with sess.patch(f"{publish_url}/{folder_id}") as resp:
        LOG.debug(f"Publishing folder {folder_id}")
        assert resp.status == 200, "HTTP Status code error"
        ans = await resp.json()
        assert ans["folderId"] == folder_id, "folder ID error"
        return ans["folderId"]


async def delete_folder(sess, folder_id):
    """Delete object folder within session.

    :param sess: HTTP session in which request call is made
    :param folder_id: id of the folder
    """
    async with sess.delete(f"{folders_url}/{folder_id}") as resp:
        LOG.debug(f"Deleting folder {folder_id}")
        assert resp.status == 204, "HTTP Status code error"


async def delete_folder_publish(sess, folder_id):
    """Delete object folder within session.

    :param sess: HTTP session in which request call is made
    :param folder_id: id of the folder
    """
    async with sess.delete(f"{folders_url}/{folder_id}") as resp:
        LOG.debug(f"Deleting folder {folder_id}")
        assert resp.status == 401, "HTTP Status code error"


async def patch_user(sess, user_id, real_user_id, json_patch):
    """Patch one user object within session, return userId.

    :param sess: HTTP session in which request call is made
    :param user_id: id of the user (current)
    :param real_user_id: id of the user in the database
    :param json_patch: JSON Patch object to use in PATCH call
    """
    async with sess.patch(f"{users_url}/current", data=json.dumps(json_patch)) as resp:
        LOG.debug(f"Updating user {real_user_id}")
        assert resp.status == 200, "HTTP Status code error"
        ans_patch = await resp.json()
        assert ans_patch["userId"] == real_user_id, "user ID error"
        return ans_patch["userId"]


async def delete_user(sess, user_id):
    """Delete user object within session.

    :param sess: HTTP session in which request call is made
    :param user_id: id of the user (current)
    """
    async with sess.delete(f"{users_url}/current") as resp:
        LOG.debug(f"Deleting user {user_id}")
        # we expect 404 as there is no frontend
        assert str(resp.url) == f"{base_url}/", "redirect url user delete differs"
        assert resp.status == 404, "HTTP Status code error"


# === Integration tests ===
async def test_crud_works(sess, schema, filename, folder_id):
    """Test REST api POST, GET and DELETE reqs.

    Tries to create new object, gets accession id and checks if correct
    resource is returned with that id. Finally deletes the object and checks it
    was deleted.

    :param sess: HTTP session in which request call is made
    :param schema: name of the schema (folder) used for testing
    :param filename: name of the file used for testing.
    :param folder_id: id of the folder used to group submission
    """
    accession_id = await post_object(sess, schema, filename)
    patch_object = [
        {"op": "add", "path": "/metadataObjects/-", "value": {"accessionId": accession_id[0], "schema": schema}}
    ]
    await patch_folder(sess, folder_id, patch_object)
    async with sess.get(f"{objects_url}/{schema}/{accession_id[0]}") as resp:
        LOG.debug(f"Checking that {accession_id[0]} JSON is in {schema}")
        assert resp.status == 200, "HTTP Status code error"
    async with sess.get(f"{objects_url}/{schema}/{accession_id[0]}?format=xml") as resp:
        LOG.debug(f"Checking that {accession_id[0]} XML is in {schema}")
        assert resp.status == 200, "HTTP Status code error"

    await delete_object(sess, schema, accession_id[0])
    async with sess.get(f"{objects_url}/{schema}/{accession_id[0]}") as resp:
        LOG.debug(f"Checking that JSON object {accession_id[0]} was deleted")
        assert resp.status == 404, "HTTP Status code error"
    async with sess.get(f"{objects_url}/{schema}/{accession_id[0]}?format=xml") as resp:
        LOG.debug(f"Checking that XML object {accession_id[0]} was deleted")
        assert resp.status == 404, "HTTP Status code error"

    async with sess.get(f"{folders_url}/{folder_id}") as resp:
        LOG.debug(f"Checking that object {accession_id} was deleted from folder {folder_id}")
        res = await resp.json()
        expected_true = not any(d["accessionId"] == accession_id for d in res["metadataObjects"])
        assert expected_true, "draft object still exists"


async def test_put_objects(sess, folder_id):
    """Test PUT reqs.

    Tries to create new object, gets accession id and checks if correct
    resource is returned with that id. Try to use PUT with JSON and expect failure,
    try to use PUT with XML and expect success.

    :param sess: HTTP session in which request call is made
    :param folder_id: id of the folder used to group submission
    """
    accession_id = await post_object(sess, "study", "SRP000539.xml")
    patch_object = [
        {"op": "add", "path": "/metadataObjects/-", "value": {"accessionId": accession_id[0], "schema": "study"}}
    ]
    await patch_folder(sess, folder_id, patch_object)
    await put_object_json(sess, "study", accession_id[0], "SRP000539.json")
    await put_object_xml(sess, "study", accession_id[0], "SRP000539_put.xml")


async def test_crud_drafts_works(sess, schema, orginal_file, update_file, folder_id):
    """Test drafts REST api POST, PUT and DELETE reqs.

    Tries to create new draft object, gets accession id and checks if correct
    resource is returned with that id. Finally deletes the object and checks it
    was deleted.

    :param sess: HTTP session in which request call is made
    :param schema: name of the schema (folder) used for testing
    :param orginal_file: name of the file used for creating object.
    :param update_file: name of the file used for updating object.
    :param folder_id: id of the folder used to group submission objects
    """
    draft_id = await post_draft_json(sess, schema, orginal_file)
    patch_draft_data = [
        {"op": "add", "path": "/drafts/-", "value": {"accessionId": draft_id, "schema": f"draft-{schema}"}}
    ]
    await patch_folder(sess, folder_id, patch_draft_data)
    accession_id = await put_draft(sess, schema, draft_id, update_file)
    async with sess.get(f"{drafts_url}/{schema}/{accession_id}") as resp:
        LOG.debug(f"Checking that {accession_id} JSON is in {schema}")
        assert resp.status == 200, "HTTP Status code error"

    await delete_draft(sess, schema, accession_id)
    async with sess.get(f"{drafts_url}/{schema}/{accession_id}") as resp:
        LOG.debug(f"Checking that JSON object {accession_id} was deleted")
        assert resp.status == 404, "HTTP Status code error"

    async with sess.get(f"{folders_url}/{folder_id}") as resp:
        LOG.debug(f"Checking that JSON object {accession_id} was deleted from folder {folder_id}")
        res = await resp.json()
        expected_true = not any(d["accessionId"] == accession_id for d in res["drafts"])
        assert expected_true, "draft object still exists"


async def test_patch_drafts_works(sess, schema, orginal_file, update_file, folder_id):
    """Test REST api POST, PATCH and DELETE reqs.

    Tries to create put and patch object, gets accession id and
    checks if correct resource is returned with that id.
    Finally deletes the object and checks it was deleted.

    :param sess: HTTP session in which request call is made
    :param schema: name of the schema (folder) used for testing
    :param orginal_file: name of the file used for creating object.
    :param update_file: name of the file used for updating object.
    :param folder_id: id of the folder used to group submission objects
    """
    draft_id = await post_draft_json(sess, schema, orginal_file)
    patch_draft_data = [
        {"op": "add", "path": "/drafts/-", "value": {"accessionId": draft_id, "schema": f"draft-{schema}"}}
    ]
    await patch_folder(sess, folder_id, patch_draft_data)
    accession_id = await patch_draft(sess, schema, draft_id, update_file)
    async with sess.get(f"{drafts_url}/{schema}/{accession_id}") as resp:
        LOG.debug(f"Checking that {accession_id} JSON is in {schema}")
        res = await resp.json()
        assert res["centerName"] == "GEOM", "object centerName content mismatch"
        assert res["alias"] == "GSE10968", "object alias content mismatch"
        assert resp.status == 200, "HTTP Status code error"

    await delete_draft(sess, schema, accession_id)
    async with sess.get(f"{drafts_url}/{schema}/{accession_id}") as resp:
        LOG.debug(f"Checking that JSON object {accession_id} was deleted")
        assert resp.status == 404, "HTTP Status code error"


async def test_querying_works(sess, folder_id):
    """Test query endpoint with working and failing query.

    :param sess: HTTP session in which request call is made
    :param folder_id: id of the folder used to group submission objects
    """
    files = await asyncio.gather(*[post_object(sess, schema, filename) for schema, filename in test_xml_files])

    for accession_id, schema in files:
        patch_folder_obj = [
            {"op": "add", "path": "/metadataObjects/-", "value": {"accessionId": accession_id, "schema": schema}}
        ]
        await patch_folder(sess, folder_id, patch_folder_obj)

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
        async with sess.get(f"{objects_url}/{schema}?{key}={value}") as resp:
            assert resp.status == expected_status, "HTTP Status code error"

    for schema, schema_queries in queries.items():
        LOG.debug(f"Querying {schema} collection with working params")
        await asyncio.gather(*[do_one_query(schema, key, value, 200) for key, value in schema_queries])
        LOG.debug("Querying {schema} collection with non-working params")
        invalid = "yoloswaggings"
        await asyncio.gather(*[do_one_query(schema, key, invalid, 404) for key, _ in schema_queries])

    await asyncio.gather(*[delete_object(sess, schema, accession_id) for accession_id, schema in files])


async def test_getting_all_objects_from_schema_works(sess, folder_id):
    """Check that /objects/study returns objects with correct pagination.

    :param sess: HTTP session in which request call is made
    :param folder_id: id of the folder used to group submission objects
    """
    # Add objects
    files = await asyncio.gather(*[post_object(sess, "study", "SRP000539.xml") for _ in range(13)])

    for accession_id, schema in files:
        patch_folder_obj = [
            {"op": "add", "path": "/metadataObjects/-", "value": {"accessionId": accession_id, "schema": schema}}
        ]
        await patch_folder(sess, folder_id, patch_folder_obj)

    # Test default values
    async with sess.get(f"{objects_url}/study") as resp:
        assert resp.status == 200
        ans = await resp.json()
        assert ans["page"]["page"] == 1
        assert ans["page"]["size"] == 10
        assert ans["page"]["totalPages"] == 2
        assert ans["page"]["totalObjects"] == 14
        assert len(ans["objects"]) == 10

    # Test with custom pagination values
    async with sess.get(f"{objects_url}/study?page=2&per_page=3") as resp:
        assert resp.status == 200
        ans = await resp.json()
        assert ans["page"]["page"] == 2
        assert ans["page"]["size"] == 3
        assert ans["page"]["totalPages"] == 5
        assert ans["page"]["totalObjects"] == 14
        assert len(ans["objects"]) == 3

    # Test with wrong pagination values
    async with sess.get(f"{objects_url}/study?page=-1") as resp:
        assert resp.status == 400
    async with sess.get(f"{objects_url}/study?per_page=0") as resp:
        assert resp.status == 400

    # Delete objects
    await asyncio.gather(*[delete_object(sess, "study", accession_id) for accession_id, _ in files])


async def test_crud_folders_works(sess):
    """Test folders REST api POST, GET, PATCH, PUBLISH and DELETE reqs.

    :param sess: HTTP session in which request call is made
    """
    # Create new folder and check its creation succeeded
    folder_data = {"name": "Mock Folder", "description": "Mock Base folder to folder ops"}
    folder_id = await post_folder(sess, folder_data)
    async with sess.get(f"{folders_url}/{folder_id}") as resp:
        LOG.debug(f"Checking that folder {folder_id} was created")
        assert resp.status == 200, "HTTP Status code error"

    # Create draft from test XML file and patch the draft into the newly created folder
    draft_id = await post_draft(sess, "sample", "SRS001433.xml")
    patch_add_draft = [
        {"op": "add", "path": "/drafts/-", "value": [{"accessionId": draft_id, "schema": "draft-sample"}]}
    ]
    folder_id = await patch_folder(sess, folder_id, patch_add_draft)
    async with sess.get(f"{folders_url}/{folder_id}") as resp:
        LOG.debug(f"Checking that folder {folder_id} was patched")
        res = await resp.json()
        assert res["folderId"] == folder_id, "expected folder id does not match"
        assert res["name"] == folder_data["name"], "expected folder name does not match"
        assert res["description"] == folder_data["description"], "folder description content mismatch"
        assert res["published"] is False, "folder is published, expected False"
        assert res["drafts"] == [{"accessionId": draft_id, "schema": "draft-sample"}], "folder drafts content mismatch"
        assert res["metadataObjects"] == [], "there are objects in folder, expected empty"

    # Get the draft from the collection within this session and post it to objects collection
    draft_data = await get_draft(sess, "sample", draft_id)
    async with sess.post(f"{objects_url}/sample", data=draft_data) as resp:
        LOG.debug("Adding draft to actual objects")
        assert resp.status == 201, "HTTP Status code error"
        ans = await resp.json()
        assert ans["accessionId"] != draft_id, "draft id does not match expected"
        accession_id = ans["accessionId"]

    # Patch folder so that original draft becomes an object in the folder
    patch_folder_move_draft = [
        {"op": "add", "path": "/metadataObjects/-", "value": [{"accessionId": accession_id, "schema": "sample"}]},
    ]
    folder_id = await patch_folder(sess, folder_id, patch_folder_move_draft)
    async with sess.get(f"{folders_url}/{folder_id}") as resp:
        LOG.debug(f"Checking that folder {folder_id} was patched")
        res = await resp.json()
        assert res["folderId"] == folder_id, "expected folder id does not match"
        assert res["published"] is False, "folder is published, expected False"
        assert res["drafts"] == [{"accessionId": draft_id, "schema": "draft-sample"}], "folder drafts content mismatch"
        assert res["metadataObjects"] == [
            {"accessionId": accession_id, "schema": "sample"}
        ], "folder metadataObjects content mismatch"

    # Publish the folder
    folder_id = await publish_folder(sess, folder_id)
    async with sess.get(f"{folders_url}/{folder_id}") as resp:
        LOG.debug(f"Checking that folder {folder_id} was patched")
        res = await resp.json()
        assert res["folderId"] == folder_id, "expected folder id does not match"
        assert res["published"] is True, "folder is not published, expected True"
        assert res["drafts"] == [], "there are drafts in folder, expected empty"
        assert res["metadataObjects"] == [
            {"accessionId": accession_id, "schema": "sample"}
        ], "folder metadataObjects content mismatch"

    # Delete folder
    await delete_folder_publish(sess, folder_id)

    async with sess.get(f"{drafts_url}/sample/{draft_id}") as resp:
        LOG.debug(f"Checking that JSON object {accession_id} was deleted")
        assert resp.status == 404, "HTTP Status code error"


async def test_crud_folders_works_no_publish(sess):
    """Test folders REST api POST, GET, PATCH, PUBLISH and DELETE reqs.

    :param sess: HTTP session in which request call is made
    """
    # Create new folder and check its creation succeeded
    folder_data = {"name": "Mock Unpublished folder", "description": "test umpublished folder"}
    folder_id = await post_folder(sess, folder_data)
    async with sess.get(f"{folders_url}/{folder_id}") as resp:
        LOG.debug(f"Checking that folder {folder_id} was created")
        assert resp.status == 200, "HTTP Status code error"

    # Create draft from test XML file and patch the draft into the newly created folder
    draft_id = await post_draft(sess, "sample", "SRS001433.xml")
    patch_add_draft = [
        {"op": "add", "path": "/drafts/-", "value": [{"accessionId": draft_id, "schema": "draft-sample"}]}
    ]
    folder_id = await patch_folder(sess, folder_id, patch_add_draft)
    async with sess.get(f"{folders_url}/{folder_id}") as resp:
        LOG.debug(f"Checking that folder {folder_id} was patched")
        res = await resp.json()
        assert res["folderId"] == folder_id, "expected folder id does not match"
        assert res["name"] == folder_data["name"], "expected folder name does not match"
        assert res["description"] == folder_data["description"], "folder description content mismatch"
        assert res["published"] is False, "folder is published, expected False"
        assert res["drafts"] == [{"accessionId": draft_id, "schema": "draft-sample"}], "folder drafts content mismatch"
        assert res["metadataObjects"] == [], "there are objects in folder, expected empty"

    # Get the draft from the collection within this session and post it to objects collection
    draft = await get_draft(sess, "sample", draft_id)
    async with sess.post(f"{objects_url}/sample", data=draft) as resp:
        LOG.debug("Adding draft to actual objects")
        assert resp.status == 201, "HTTP Status code error"
        ans = await resp.json()
        assert ans["accessionId"] != draft_id, "draft id does not match expected"
        accession_id = ans["accessionId"]

    # Patch folder so that original draft becomes an object in the folder
    patch_folder_move_draft = [
        {"op": "add", "path": "/metadataObjects/-", "value": [{"accessionId": accession_id, "schema": "sample"}]},
    ]
    folder_id = await patch_folder(sess, folder_id, patch_folder_move_draft)
    async with sess.get(f"{folders_url}/{folder_id}") as resp:
        LOG.debug(f"Checking that folder {folder_id} was patched")
        res = await resp.json()
        assert res["folderId"] == folder_id, "expected folder id does not match"
        assert res["published"] is False, "folder is published, expected False"
        assert res["drafts"] == [{"accessionId": draft_id, "schema": "draft-sample"}], "folder drafts content mismatch"
        assert res["metadataObjects"] == [
            {"accessionId": accession_id, "schema": "sample"}
        ], "folder metadataObjects content mismatch"

    # Delete folder
    await delete_folder(sess, folder_id)
    async with sess.get(f"{folders_url}/{folder_id}") as resp:
        LOG.debug(f"Checking that folder {folder_id} was deleted")
        assert resp.status == 404, "HTTP Status code error"

    async with sess.get(f"{users_url}/current") as resp:
        LOG.debug(f"Checking that folder {folder_id} was deleted from current user")
        res = await resp.json()
        expected_true = not any(d == accession_id for d in res["folders"])
        assert expected_true, "folder still exists at user"


async def test_getting_paginated_folders(sess):
    """Check that /folders returns folders with correct paginations.

    :param sess: HTTP session in which request call is made
    """
    # Test default values
    async with sess.get(f"{folders_url}") as resp:
        # The folders received here are from previous
        # tests where the folders were not deleted
        assert resp.status == 200
        ans = await resp.json()
        assert ans["page"]["page"] == 1
        assert ans["page"]["size"] == 5
        assert ans["page"]["totalPages"] == 2
        assert ans["page"]["totalFolders"] == 6
        assert len(ans["folders"]) == 5

    # Test with custom pagination values
    async with sess.get(f"{folders_url}?page=2&per_page=3") as resp:
        assert resp.status == 200
        ans = await resp.json()
        assert ans["page"]["page"] == 2
        assert ans["page"]["size"] == 3
        assert ans["page"]["totalPages"] == 2
        assert ans["page"]["totalFolders"] == 6
        assert len(ans["folders"]) == 3

    # Test querying only published folders
    async with sess.get(f"{folders_url}?published=true") as resp:
        assert resp.status == 200
        ans = await resp.json()
        assert ans["page"]["page"] == 1
        assert ans["page"]["size"] == 5
        assert ans["page"]["totalPages"] == 1
        assert ans["page"]["totalFolders"] == 1
        assert len(ans["folders"]) == 1

    # Test querying only draft folders
    async with sess.get(f"{folders_url}?published=false") as resp:
        assert resp.status == 200
        ans = await resp.json()
        assert ans["page"]["page"] == 1
        assert ans["page"]["size"] == 5
        assert ans["page"]["totalPages"] == 1
        assert ans["page"]["totalFolders"] == 5
        assert len(ans["folders"]) == 5

    # Test with wrong pagination values
    async with sess.get(f"{folders_url}?page=-1") as resp:
        assert resp.status == 400
    async with sess.get(f"{folders_url}?per_page=0") as resp:
        assert resp.status == 400
    async with sess.get(f"{folders_url}?published=asdf") as resp:
        assert resp.status == 400


async def test_getting_user_drafts(sess):
    """Test querying user's drafts or folders with GET user request.

    :param sess: HTTP session in which request call is made
    """
    # Get real user ID
    async with sess.get(f"{users_url}/{user_id}") as resp:
        LOG.debug(f"Reading user {user_id}")
        assert resp.status == 200, "HTTP Status code error"
        response = await resp.json()
        real_user_id = response["userId"]

    # Patch user to have a draft
    draft_id = await post_draft_json(sess, "study", "SRP000539.json")
    patch_drafts_user = [
        {"op": "add", "path": "/drafts/-", "value": {"accessionId": draft_id, "schema": "draft-study"}}
    ]
    await patch_user(sess, user_id, real_user_id, patch_drafts_user)

    # Test querying for list of user draft templates
    async with sess.get(f"{users_url}/{user_id}?items=drafts") as resp:
        LOG.debug(f"Reading user {user_id} drafts")
        assert resp.status == 200, "HTTP Status code error"
        ans = await resp.json()
        assert ans["page"]["page"] == 1
        assert ans["page"]["size"] == 5
        assert ans["page"]["totalPages"] == 1
        assert ans["page"]["totalDrafts"] == 1
        assert len(ans["drafts"]) == 1

    async with sess.get(f"{users_url}/{user_id}?items=drafts&per_page=3") as resp:
        LOG.debug(f"Reading user {user_id} drafts")
        assert resp.status == 200, "HTTP Status code error"
        ans = await resp.json()
        assert ans["page"]["page"] == 1
        assert ans["page"]["size"] == 3
        assert len(ans["drafts"]) == 1

    await delete_draft(sess, "study", draft_id)  # Future tests will assume the drafts key is empty

    # Test querying for the list of folders
    async with sess.get(f"{users_url}/{user_id}?items=folders") as resp:
        LOG.debug(f"Reading user {user_id} folder list")
        assert resp.status == 200, "HTTP Status code error"
        ans = await resp.json()
        assert len(ans["folderIds"]) == 6

    # Test the same with a bad query param
    async with sess.get(f"{users_url}/{user_id}?items=bad") as resp:
        LOG.debug(f"Reading user {user_id} but with faulty item descriptor")
        assert resp.status == 400, "HTTP Status code error"


async def test_crud_users_works(sess):
    """Test users REST api GET, PATCH and DELETE reqs.

    :param sess: HTTP session in which request call is made
    """
    # Check user exists in database (requires an user object to be mocked)
    async with sess.get(f"{users_url}/{user_id}") as resp:
        LOG.debug(f"Reading user {user_id}")
        assert resp.status == 200, "HTTP Status code error"
        response = await resp.json()
        real_user_id = response["userId"]

    # Add user to session and create a patch to add folder to user
    folder_not_published = {"name": "Mock User Folder", "description": "Mock folder for testing users"}
    folder_id = await post_folder(sess, folder_not_published)
    patch_add_folder = [{"op": "add", "path": "/folders/-", "value": [folder_id]}]
    await patch_user(sess, user_id, real_user_id, patch_add_folder)
    async with sess.get(f"{users_url}/{user_id}") as resp:
        LOG.debug(f"Checking that folder {folder_id} was added")
        res = await resp.json()
        assert res["userId"] == real_user_id, "user id does not match"
        assert res["name"] == f"{test_user_given} {test_user_family}", "user name mismatch"
        assert res["drafts"] == [], "user drafts content mismatch"
        assert folder_id in res["folders"], "folder added missing mismatch"

    folder_published = {"name": "Another test Folder", "description": "Test published folder does not get deleted"}
    publish_folder_id = await post_folder(sess, folder_published)
    await publish_folder(sess, publish_folder_id)
    async with sess.get(f"{folders_url}/{publish_folder_id}") as resp:
        LOG.debug(f"Checking that folder {publish_folder_id} was published")
        res = await resp.json()
        assert res["published"] is True, "folder is not published, expected True"

    folder_not_published = {"name": "Delete Folder", "description": "Mock folder to delete while testing users"}
    delete_folder_id = await post_folder(sess, folder_not_published)
    patch_delete_folder = [{"op": "add", "path": "/folders/-", "value": [delete_folder_id]}]
    await patch_user(sess, user_id, real_user_id, patch_delete_folder)
    async with sess.get(f"{users_url}/{user_id}") as resp:
        LOG.debug(f"Checking that folder {delete_folder_id} was added")
        res = await resp.json()
        assert delete_folder_id in res["folders"], "deleted folder added does not exists"
    await delete_folder(sess, delete_folder_id)
    async with sess.get(f"{users_url}/{user_id}") as resp:
        LOG.debug(f"Checking that folder {delete_folder_id} was deleted")
        res = await resp.json()
        assert delete_folder_id not in res["folders"], "delete folder still exists at user"

    draft_id = await post_draft_json(sess, "study", "SRP000539.json")
    patch_drafts_user = [
        {"op": "add", "path": "/drafts/-", "value": {"accessionId": draft_id, "schema": "draft-study"}}
    ]
    await patch_user(sess, user_id, real_user_id, patch_drafts_user)
    async with sess.get(f"{users_url}/{user_id}") as resp:
        LOG.debug(f"Checking that draft {draft_id} was added")
        res = await resp.json()
        assert res["drafts"][0]["accessionId"] == draft_id, "draft added does not exists"

    await delete_draft(sess, "study", draft_id)

    async with sess.get(f"{users_url}/{user_id}") as resp:
        LOG.debug(f"Checking that draft {draft_id} was added")
        res = await resp.json()
        assert len(res["drafts"]) == 0, "draft was not deleted from users"

    # Delete user
    await delete_user(sess, user_id)
    # 401 means API is innacessible thus session ended
    # this check is not needed but good to do
    async with sess.get(f"{users_url}/{user_id}") as resp:
        LOG.debug(f"Checking that user {user_id} was deleted")
        assert resp.status == 401, "HTTP Status code error"


async def test_get_folders(sess, folder_id: str):
    """Test folders REST api GET .

    :param sess: HTTP session in which request call is made
    :param folder_id: id of the folder used to group submission objects
    """
    async with sess.get(f"{folders_url}") as resp:
        LOG.debug(f"Reading folder {folder_id}")
        assert resp.status == 200, "HTTP Status code error"
        response = await resp.json()
        assert len(response["folders"]) == 1
        assert response["page"] == {"page": 1, "size": 5, "totalPages": 1, "totalFolders": 1}
        assert response["folders"][0]["folderId"] == folder_id


async def test_get_folders_objects(sess, folder_id: str):
    """Test folders REST api GET with objects.

    :param sess: HTTP session in which request call is made
    :param folder_id: id of the folder used to group submission objects
    """
    accession_id = await post_object_json(sess, "study", "SRP000539.json")
    patch_add_object = [
        {"op": "add", "path": "/metadataObjects/-", "value": {"accessionId": accession_id, "schema": "study"}}
    ]
    await patch_folder(sess, folder_id, patch_add_object)
    async with sess.get(f"{folders_url}") as resp:
        LOG.debug(f"Reading folder {folder_id}")
        assert resp.status == 200, "HTTP Status code error"
        response = await resp.json()
        assert len(response["folders"]) == 1
        assert response["folders"][0]["metadataObjects"][0]["accessionId"] == accession_id
        assert "tags" not in response["folders"][0]["metadataObjects"][0]
    patch_add_more_object = [
        {
            "op": "add",
            "path": "/metadataObjects/0/tags",
            "value": {"submissionType": "Form"},
        }
    ]
    await patch_folder(sess, folder_id, patch_add_more_object)
    async with sess.get(f"{folders_url}") as resp:
        LOG.debug(f"Reading folder {folder_id}")
        assert resp.status == 200, "HTTP Status code error"
        response = await resp.json()
        assert len(response["folders"]) == 1
        assert response["folders"][0]["metadataObjects"][0]["accessionId"] == accession_id
        assert response["folders"][0]["metadataObjects"][0]["tags"]["submissionType"] == "Form"

    patch_change_tags_object = [
        {
            "op": "replace",
            "path": "/metadataObjects/0/tags",
            "value": {"submissionType": "XML"},
        }
    ]
    await patch_folder(sess, folder_id, patch_change_tags_object)
    async with sess.get(f"{folders_url}") as resp:
        LOG.debug(f"Reading folder {folder_id}")
        assert resp.status == 200, "HTTP Status code error"
        response = await resp.json()
        assert len(response["folders"]) == 1
        assert response["folders"][0]["metadataObjects"][0]["accessionId"] == accession_id
        assert response["folders"][0]["metadataObjects"][0]["tags"]["submissionType"] == "XML"


async def test_submissions_work(sess, folder_id):
    """Test actions in submission XML files.

    :param sess: HTTP session in which request call is made
    :param folder_id: id of the folder used to group submission objects
    """
    # Post original submission with two 'add' actions
    sub_files = [("submission", "ERA521986_valid.xml"), ("study", "SRP000539.xml"), ("sample", "SRS001433.xml")]
    submission_data = await create_multi_file_request_data(sub_files)
    async with sess.post(f"{submit_url}", data=submission_data) as resp:
        LOG.debug("Checking initial submission worked")
        assert resp.status == 200, "HTTP Status code error"
        res = await resp.json()
        assert len(res) == 2, "expected 2 objects"
        assert res[0]["schema"] == "study", "expected first element to be study"
        assert res[1]["schema"] == "sample", "expected second element to be sample"
        study_access_id = res[0]["accessionId"]
        patch = [
            {
                "op": "add",
                "path": "/metadataObjects/-",
                "value": {"accessionId": res[0]["accessionId"], "schema": res[0]["schema"]},
            },
            {
                "op": "add",
                "path": "/metadataObjects/-",
                "value": {"accessionId": res[1]["accessionId"], "schema": res[1]["schema"]},
            },
        ]
        await patch_folder(sess, folder_id, patch)

    # Sanity check that the study object was inserted correctly before modifying it
    async with sess.get(f"{objects_url}/study/{study_access_id}") as resp:
        LOG.debug("Sanity checking that previous object was added correctly")
        assert resp.status == 200, "HTTP Status code error"
        res = await resp.json()
        assert res["accessionId"] == study_access_id, "study accession id does not match"
        assert res["alias"] == "GSE10966", "study alias does not match"
        assert res["descriptor"]["studyTitle"] == (
            "Highly integrated epigenome maps in Arabidopsis - whole genome shotgun bisulfite sequencing"
        ), "study title does not match"

    # Give test file the correct accession id
    LOG.debug("Sharing the correct accession ID created in this test instance")
    mod_study = testfiles_root / "study" / "SRP000539_modified.xml"
    tree = ET.parse(mod_study)
    root = tree.getroot()
    for elem in root.iter("STUDY"):
        elem.set("accession", study_access_id)
    tree.write(mod_study, encoding="utf-8")

    # Post new submission that modifies previously added study object and validates it
    sub_files = [("submission", "ERA521986_modify.xml"), ("study", "SRP000539_modified.xml")]
    more_submission_data = await create_multi_file_request_data(sub_files)
    async with sess.post(f"{submit_url}", data=more_submission_data) as resp:
        LOG.debug("Checking object in initial submission was modified")
        assert resp.status == 200, "HTTP Status code error"
        res = await resp.json()
        assert len(res) == 2, "expected 2 objects"
        new_study_access_id = res[0]["accessionId"]
        assert study_access_id == new_study_access_id

    # Check the modified object was inserted correctly
    async with sess.get(f"{objects_url}/study/{new_study_access_id}") as resp:
        LOG.debug("Checking that previous object was modified correctly")
        assert resp.status == 200, "HTTP Status code error"
        res = await resp.json()
        assert res["accessionId"] == new_study_access_id, "study accession id does not match"
        assert res["alias"] == "GSE10966", "study alias does not match"
        assert res["descriptor"]["studyTitle"] == (
            "Different title for testing purposes"
        ), "updated study title does not match"

    # Remove the accession id that was used for testing from test file
    LOG.debug("Sharing the correct accession ID created in this test instance")
    mod_study = testfiles_root / "study" / "SRP000539_modified.xml"
    tree = ET.parse(mod_study)
    root = tree.getroot()
    for elem in root.iter("STUDY"):
        del elem.attrib["accession"]
    tree.write(mod_study, encoding="utf-8")


async def test_health_check(sess):
    """Test the health check endpoint.

    :param sess: HTTP session in which request call is made
    """
    async with sess.get(f"{base_url}/health") as resp:
        LOG.debug("Checking that health status is ok")
        assert resp.status == 200, "HTTP Status code error"
        res = await resp.json()
        assert res["status"] == "Ok"
        assert res["services"]["database"]["status"] == "Ok"


async def main():
    """Launch different test tasks and run them."""

    async with aiohttp.ClientSession() as sess:

        LOG.debug("=== Login other mock user ===")
        await login(sess, other_test_user, other_test_user_given, other_test_user_family)

        # Test add, modify, validate and release action with submissions
        # added to validate that objects belong to a specific user
        LOG.debug("=== Testing actions within submissions ===")
        submission_folder = {
            "name": "submission test 1",
            "description": "submission test folder 1",
        }
        submission_folder_id = await post_folder(sess, submission_folder)
        await test_get_folders(sess, submission_folder_id)
        await test_get_folders_objects(sess, submission_folder_id)
        await test_submissions_work(sess, submission_folder_id)

    async with aiohttp.ClientSession() as sess:
        LOG.debug("=== Login mock user ===")
        await login(sess, test_user, test_user_given, test_user_family)

        # Test adding and getting objects
        LOG.debug("=== Testing basic CRUD operations ===")
        basic_folder = {
            "name": "basic test",
            "description": "basic test folder",
        }
        basic_folder_id = await post_folder(sess, basic_folder)

        await asyncio.gather(*[test_crud_works(sess, schema, file, basic_folder_id) for schema, file in test_xml_files])

        put_object_folder = {
            "name": "test put object",
            "description": "put object test folder",
        }
        put_object_folder = await post_folder(sess, put_object_folder)

        await test_put_objects(sess, put_object_folder)

        # Test adding and getting draft objects
        LOG.debug("=== Testing basic CRUD drafts operations ===")
        draft_folder = {
            "name": "basic test draft",
            "description": "basic test draft folder",
        }
        draft_folder_id = await post_folder(sess, draft_folder)
        await asyncio.gather(
            *[
                test_crud_drafts_works(sess, schema, file, file2, draft_folder_id)
                for schema, file, file2 in test_json_files
            ]
        )

        # Test patch and put
        LOG.debug("=== Testing patch and put drafts operations ===")
        await test_crud_drafts_works(sess, "sample", "SRS001433.json", "put.json", draft_folder_id)
        await test_patch_drafts_works(sess, "study", "SRP000539.json", "patch.json", draft_folder_id)

        # Test queries
        LOG.debug("=== Testing queries ===")
        query_folder = {
            "name": "basic test query",
            "description": "basic test query folder",
        }
        query_folder_id = await post_folder(sess, query_folder)
        await test_querying_works(sess, query_folder_id)

        # Test /objects/study endpoint for query pagination
        LOG.debug("=== Testing getting all objects & pagination ===")
        pagination_folder = {
            "name": "basic test pagination",
            "description": "basic test pagination folder",
        }
        pagination_folder_id = await post_folder(sess, pagination_folder)
        await test_getting_all_objects_from_schema_works(sess, pagination_folder_id)

        # Test creating, reading, updating and deleting folders
        LOG.debug("=== Testing basic CRUD folder operations ===")
        await test_crud_folders_works(sess)
        await test_crud_folders_works_no_publish(sess)

        # Test getting a list of folders and draft templates owned by the user
        LOG.debug("=== Testing getting folders, draft folders and draft templates with pagination ===")
        await test_getting_paginated_folders(sess)
        await test_getting_user_drafts(sess)

        # Test add, modify, validate and release action with submissions
        LOG.debug("=== Testing actions within submissions ===")
        submission_folder = {
            "name": "submission test",
            "description": "submission test folder",
        }
        submission_folder_id = await post_folder(sess, submission_folder)
        await test_submissions_work(sess, submission_folder_id)

        # Test health status check
        LOG.debug("=== Testing health status check ===")
        await test_health_check(sess)

        # Test reading, updating and deleting users
        # this needs to be done last as it deletes users
        LOG.debug("=== Testing basic CRUD user operations ===")
        await test_crud_users_works(sess)

    # Remove the remaining user in the test database
    async with aiohttp.ClientSession() as sess:
        await login(sess, other_test_user, other_test_user_given, other_test_user_family)
        async with sess.get(f"{users_url}/{user_id}") as resp:
            LOG.debug(f"Reading user {user_id}")
            assert resp.status == 200, "HTTP Status code error"
            response = await resp.json()
            real_user_id = response["userId"]
        await delete_user(sess, real_user_id)


if __name__ == "__main__":
    asyncio.run(main())
