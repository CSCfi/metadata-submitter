"""
Run integration tests against backend api endpoints.

Deleting from db is currently not supported, objects added to db in different
should be taken into account.
"""
import asyncio
import json
import logging
import os
import re
import urllib
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import aiofiles
import aiohttp
from aiohttp import FormData
from motor.motor_asyncio import AsyncIOMotorClient

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
    ("dataset", "dataset.json", "dataset.json"),
    ("run", "ERR000076.json", "ERR000076.json"),
    ("experiment", "ERX000119.json", "ERX000119.json"),
    ("analysis", "ERZ266973.json", "ERZ266973.json"),
]
base_url = os.getenv("BASE_URL", "http://localhost:5430")
mock_auth_url = os.getenv("OIDC_URL_TEST", "http://localhost:8000")
objects_url = f"{base_url}/objects"
drafts_url = f"{base_url}/drafts"
templates_url = f"{base_url}/templates"
folders_url = f"{base_url}/folders"
users_url = f"{base_url}/users"
submit_url = f"{base_url}/submit"
publish_url = f"{base_url}/publish"
metax_url = f"{os.getenv('METAX_URL', 'http://localhost:8002')}/rest/v2/datasets"
# to form direct contact to db with create_folder()
DATABASE = os.getenv("MONGO_DATABASE", "default")
AUTHDB = os.getenv("MONGO_AUTHDB", "admin")
HOST = os.getenv("MONGO_HOST", "localhost:27017")
TLS = os.getenv("MONGO_SSL", False)

user_id = "current"
test_user_given = "Given"
test_user_family = "Family"
test_user = "user_given@test.what"

other_test_user_given = "Mock"
other_test_user_family = "Family"
other_test_user = "mock_user@test.what"


# === Helper functions ===
async def login(sess, sub, given, family):
    """Mock login."""
    params = {
        "sub": sub,
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
        c_type = "text/xml" if filename[-3:] == "xml" else "text/csv"
        request_data.add_field(schema.upper(), await f.read(), filename=filename, content_type=c_type)
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
            request_data.add_field(
                schema.upper(),
                await f.read(),
                filename=filename,
                content_type="text/xml",
            )
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


async def post_object(sess, schema, folder_id, filename):
    """Post one metadata object within session, returns accessionId.

    :param sess: HTTP session in which request call is made
    :param schema: name of the schema (folder) used for testing
    :param filename: name of the file used for testing.
    """
    request_data = await create_request_data(schema, filename)
    async with sess.post(f"{objects_url}/{schema}", params={"folder": folder_id}, data=request_data) as resp:
        LOG.debug(f"Adding new object to {schema}, via XML/CSV file {filename}")
        assert resp.status == 201, f"HTTP Status code error, got {resp.status}"
        ans = await resp.json()
        return ans if isinstance(ans, list) else ans["accessionId"], schema


async def post_object_expect_status(sess, schema, folder_id, filename, status):
    """Post one metadata object within session, returns accessionId.

    :param sess: HTTP session in which request call is made
    :param schema: name of the schema (folder) used for testing
    :param filename: name of the file used for testing.
    """
    request_data = await create_request_data(schema, filename)
    async with sess.post(f"{objects_url}/{schema}", params={"folder": folder_id}, data=request_data) as resp:
        LOG.debug(f"Adding new object to {schema}, via XML/CSV file {filename} and expecting status: {status}")
        assert resp.status == status, f"HTTP Status code error, got {resp.status}"
        if status < 400:
            ans = await resp.json()
            return ans if isinstance(ans, list) else ans["accessionId"], schema


async def post_object_json(sess, schema, folder_id, filename):
    """Post & put one metadata object within session, returns accessionId.

    :param sess: HTTP session in which request call is made
    :param schema: name of the schema (folder) used for testing
    :param filename: name of the file used for testing.
    """
    request_data = await create_request_json_data(schema, filename)
    async with sess.post(f"{objects_url}/{schema}", params={"folder": folder_id}, data=request_data) as resp:
        LOG.debug(f"Adding new object to {schema}, via JSON file {filename}")
        assert resp.status == 201, f"HTTP Status code error, got {resp.status}"
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
        assert resp.status == 204, f"HTTP Status code error, got {resp.status}"


async def post_draft(sess, schema, folder_id, filename):
    """Post one draft metadata object within session, returns accessionId.

    :param sess: HTTP session in which request call is made
    :param schema: name of the schema (folder) used for testing
    :param filename: name of the file used for testing.
    """
    request_data = await create_request_data(schema, filename)
    async with sess.post(f"{drafts_url}/{schema}", params={"folder": folder_id}, data=request_data) as resp:
        LOG.debug(f"Adding new draft object to {schema}, via XML file {filename}")
        assert resp.status == 201, f"HTTP Status code error, got {resp.status}"
        ans = await resp.json()
        return ans["accessionId"]


async def post_draft_json(sess, schema, folder_id, filename):
    """Post & put one metadata object within session, returns accessionId.

    :param sess: HTTP session in which request call is made
    :param schema: name of the schema (folder) used for testing
    :param filename: name of the file used for testing.
    """
    request_data = await create_request_json_data(schema, filename)
    async with sess.post(f"{drafts_url}/{schema}", params={"folder": folder_id}, data=request_data) as resp:
        LOG.debug(f"Adding new draft object to {schema}, via JSON file {filename}")
        assert resp.status == 201, f"HTTP Status code error, got {resp.status}"
        ans = await resp.json()
        return ans["accessionId"]


async def get_draft(sess, schema, draft_id, expected_status=200):
    """Get and return a drafted metadata object.

    :param sess: HTTP session in which request call is made
    :param schema: name of the schema (folder) used for testing
    :param draft_id: id of the draft
    """
    async with sess.get(f"{drafts_url}/{schema}/{draft_id}") as resp:
        LOG.debug(f"Checking that {draft_id} JSON exists")
        assert resp.status == expected_status, f"HTTP Status code error, got {resp.status}"
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
        assert resp.status == 200, f"HTTP Status code error, got {resp.status}"
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
        assert resp.status == 415, f"HTTP Status code error, got {resp.status}"


async def patch_object_json(sess, schema, accession_id, update_filename):
    """Patch one metadata object within session, returns accessionId.

    :param sess: HTTP session in which request call is made
    :param schema: name of the schema (folder) used for testing
    :param draft_id: id of the draft
    :param update_filename: name of the file used to use for updating data.
    """
    request_data = await create_request_json_data(schema, update_filename)
    async with sess.patch(f"{objects_url}/{schema}/{accession_id}", data=request_data) as resp:
        LOG.debug(f"Try to patch object in {schema}")
        assert resp.status == 200, f"HTTP Status code error, got {resp.status}"
        ans_put = await resp.json()
        assert ans_put["accessionId"] == accession_id, "accession ID error"
        return ans_put["accessionId"]


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
        assert resp.status == 200, f"HTTP Status code error, got {resp.status}"
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
        assert resp.status == 200, f"HTTP Status code error, got {resp.status}"
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
        assert resp.status == 204, f"HTTP Status code error, got {resp.status}"


async def post_template_json(sess, schema, filename):
    """Post one metadata object within session, returns accessionId.

    :param sess: HTTP session in which request call is made
    :param schema: name of the schema (folder) used for testing
    :param filename: name of the file used for testing.
    """
    request_data = await create_request_json_data(schema, filename)
    async with sess.post(f"{templates_url}/{schema}", data=request_data) as resp:
        LOG.debug(f"Adding new template object to {schema}, via JSON file {filename}")
        assert resp.status == 201, f"HTTP Status code error, got {resp.status}"
        ans = await resp.json()
        if isinstance(ans, list):
            return ans
        else:
            return ans["accessionId"]


async def get_template(sess, schema, template_id):
    """Get and return a drafted metadata object.

    :param sess: HTTP session in which request call is made
    :param schema: name of the schema (folder) used for testing
    :param template_id: id of the draft
    """
    async with sess.get(f"{templates_url}/{schema}/{template_id}") as resp:
        LOG.debug(f"Checking that {template_id} JSON exists")
        assert resp.status == 200, f"HTTP Status code error, got {resp.status}"
        ans = await resp.json()
        return json.dumps(ans)


async def patch_template(sess, schema, template_id, update_filename):
    """Patch one metadata object within session, return accessionId.

    :param sess: HTTP session in which request call is made
    :param schema: name of the schema (folder) used for testing
    :param template_id: id of the draft
    :param update_filename: name of the file used to use for updating data.
    """
    request_data = await create_request_json_data(schema, update_filename)
    async with sess.patch(f"{templates_url}/{schema}/{template_id}", data=request_data) as resp:
        LOG.debug(f"Update draft object in {schema}")
        assert resp.status == 200, f"HTTP Status code error, got {resp.status}"
        ans_put = await resp.json()
        assert ans_put["accessionId"] == template_id, "accession ID error"
        return ans_put["accessionId"]


async def delete_template(sess, schema, template_id):
    """Delete metadata object within session.

    :param sess: HTTP session in which request call is made
    :param schema: name of the schema (folder) used for testing
    :param template_id: id of the draft
    """
    async with sess.delete(f"{templates_url}/{schema}/{template_id}") as resp:
        LOG.debug(f"Deleting template object {template_id} from {schema}")
        assert resp.status == 204, f"HTTP Status code error, got {resp.status}"


async def post_folder(sess, data):
    """Post one object folder within session, returns folderId.

    :param sess: HTTP session in which request call is made
    :param data: data used to update the folder
    """
    async with sess.post(f"{folders_url}", data=json.dumps(data)) as resp:
        LOG.debug("Adding new folder")
        ans = await resp.json()
        assert resp.status == 201, f"HTTP Status code error {resp.status} {ans}"
        return ans["folderId"]


async def patch_folder(sess, folder_id, json_patch):
    """Patch one object folder within session, return folderId.

    :param sess: HTTP session in which request call is made
    :param folder_id: id of the folder
    :param json_patch: JSON Patch object to use in PATCH call
    """
    async with sess.patch(f"{folders_url}/{folder_id}", data=json.dumps(json_patch)) as resp:
        LOG.debug(f"Updating folder {folder_id}")
        assert resp.status == 200, f"HTTP Status code error, got {resp.status}"
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
        assert resp.status == 200, f"HTTP Status code error, got {resp.status}"
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
        assert resp.status == 204, f"HTTP Status code error, got {resp.status}"


async def delete_folder_publish(sess, folder_id):
    """Delete object folder within session.

    :param sess: HTTP session in which request call is made
    :param folder_id: id of the folder
    """
    async with sess.delete(f"{folders_url}/{folder_id}") as resp:
        LOG.debug(f"Deleting folder {folder_id}")
        assert resp.status == 401, f"HTTP Status code error, got {resp.status}"


async def create_folder(data, user):
    """Create new object folder to database.

    :param data: Data as dict to be saved to database
    :param user: User id to which data is assigned
    :returns: Folder id for the folder inserted to database
    """
    LOG.info("Creating new folder")
    url = f"mongodb://{AUTHDB}:{AUTHDB}@{HOST}/{DATABASE}?authSource=admin"
    db_client = AsyncIOMotorClient(url, connectTimeoutMS=1000, serverSelectionTimeoutMS=1000)
    database = db_client[DATABASE]

    folder_id = uuid4().hex
    data["folderId"] = folder_id
    data["text_name"] = " ".join(re.split("[\\W_]", data["name"]))
    data["drafts"] = []
    data["metadataObjects"] = []
    try:
        await database["folder"].insert_one(data)
        find_by_id = {"userId": user}
        append_op = {"$push": {"folders": {"$each": [folder_id], "$position": 0}}}
        await database["user"].find_one_and_update(
            find_by_id, append_op, projection={"_id": False}, return_document=True
        )
        return folder_id

    except Exception as e:
        LOG.error(f"Folder creation failed due to {str(e)}")


async def patch_user(sess, user_id, real_user_id, json_patch):
    """Patch one user object within session, return userId.

    :param sess: HTTP session in which request call is made
    :param user_id: id of the user (current)
    :param real_user_id: id of the user in the database
    :param json_patch: JSON Patch object to use in PATCH call
    """
    async with sess.patch(f"{users_url}/current", data=json.dumps(json_patch)) as resp:
        LOG.debug(f"Updating user {real_user_id}")
        assert resp.status == 200, f"HTTP Status code error, got {resp.status}"
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
        assert resp.status == 404, f"HTTP Status code error, got {resp.status}"


def extract_folders_object(res, accession_id, draft):
    """Extract object from folder metadataObjects with provided accessionId.

    :param res: JSON parsed responce from folder query request
    :param accession_id: accession ID of reviwed object
    :returns: dict of object entry in folder
    """
    object = "drafts" if draft else "metadataObjects"
    actual_res = next(obj for obj in res[object] if obj["accessionId"] == accession_id)
    return actual_res


async def check_folders_object_patch(sess, folder_id, schema, accession_id, title, filename, draft=False):
    """Check that draft is added correctly to folder.

    Get draft or metadata object from the folder and assert with data
    returned from object endpoint itself.

    :param sess: HTTP session in which request call is made
    :param folder_id: id of the folder
    :param schema: name of the schema (folder) used for testing
    :param accession_id: accession ID of reviwed object
    :param title: title of reviwed object
    :param filename: name of the file used for inserting data
    :param draft: indication of object draft status, default False
    """
    sub_type = "Form" if filename.split(".")[-1] == "json" else filename.split(".")[-1].upper()
    async with sess.get(f"{folders_url}/{folder_id}") as resp:
        res = await resp.json()
        try:
            actual = extract_folders_object(res, accession_id, draft)
            expected = {
                "accessionId": accession_id,
                "schema": schema if not draft else f"draft-{schema}",
                "tags": {
                    "submissionType": sub_type,
                    "displayTitle": title,
                    "fileName": filename,
                },
            }
            if sub_type == "Form":
                del expected["tags"]["fileName"]
            assert actual == expected, "actual end expected data did not match"
        except StopIteration:
            pass
        return schema


# === Integration tests ===
async def test_crud_works(sess, schema, filename, folder_id):
    """Test REST api POST, GET and DELETE reqs.

    Tries to create new object, gets accession id and checks if correct
    resource is returned with that id. Finally deletes the object and checks it
    was deleted.

    :param sess: HTTP session in which request call is made
    :param schema: name of the schema (folder) used for testing
    :param filename: name of the file used for testing
    :param folder_id: id of the folder used to group submission
    """
    accession_id = await post_object(sess, schema, folder_id, filename)
    async with sess.get(f"{objects_url}/{schema}/{accession_id[0]}") as resp:
        LOG.debug(f"Checking that {accession_id[0]} JSON is in {schema}")
        assert resp.status == 200, f"HTTP Status code error, got {resp.status}"
        res = await resp.json()
        title = res["descriptor"].get("studyTitle", "") if schema == "study" else res.get("title", "")
    await check_folders_object_patch(sess, folder_id, schema, accession_id[0], title, filename)
    async with sess.get(f"{objects_url}/{schema}/{accession_id[0]}?format=xml") as resp:
        LOG.debug(f"Checking that {accession_id[0]} XML is in {schema}")
        assert resp.status == 200, f"HTTP Status code error, got {resp.status}"

    await delete_object(sess, schema, accession_id[0])
    async with sess.get(f"{objects_url}/{schema}/{accession_id[0]}") as resp:
        LOG.debug(f"Checking that JSON object {accession_id[0]} was deleted")
        assert resp.status == 404, f"HTTP Status code error, got {resp.status}"
    async with sess.get(f"{objects_url}/{schema}/{accession_id[0]}?format=xml") as resp:
        LOG.debug(f"Checking that XML object {accession_id[0]} was deleted")
        assert resp.status == 404, f"HTTP Status code error, got {resp.status}"

    async with sess.get(f"{folders_url}/{folder_id}") as resp:
        LOG.debug(f"Checking that object {accession_id[0]} was deleted from folder {folder_id}")
        res = await resp.json()
        expected_true = not any(d["accessionId"] == accession_id[0] for d in res["metadataObjects"])
        assert expected_true, f"object {accession_id[0]} still exists"


async def test_csv(sess, folder_id):
    """Test CRUD for a submitted CSV file.

    Test tries with good csv file first for sample object, after which we try with empty file.
    After this we try with study object which is not allowed.

    :param sess: HTTP session in which request call is made
    :param schema: name of the schema (folder) used for testing
    :param filename: name of the file used for testing
    :param folder_id: id of the folder used to group submission
    """
    _schema = "sample"
    _filename = "EGAformat.csv"
    accession_id = await post_object(sess, _schema, folder_id, _filename)
    # there are 3 rows and we expected to get 3rd
    assert len(accession_id[0]) == 3, f"expected nb of CSV entries does not match, we got: {len(accession_id)}"
    _first_csv_row_id = accession_id[0][0]["accessionId"]

    async with sess.get(f"{objects_url}/{_schema}/{_first_csv_row_id}") as resp:
        LOG.debug(f"Checking that {_first_csv_row_id} JSON is in {_schema}")
        assert resp.status == 200, f"HTTP Status code error, got {resp.status}"
        res = await resp.json()
        title = res.get("title", "")
    await check_folders_object_patch(sess, folder_id, _schema, accession_id, title, _filename)

    await delete_object(sess, _schema, _first_csv_row_id)
    async with sess.get(f"{objects_url}/{_schema}/{_first_csv_row_id}") as resp:
        LOG.debug(f"Checking that JSON object {_first_csv_row_id} was deleted")
        assert resp.status == 404, f"HTTP Status code error, got {resp.status}"

    async with sess.get(f"{folders_url}/{folder_id}") as resp:
        LOG.debug(f"Checking that object {_first_csv_row_id} was deleted from folder {folder_id}")
        res = await resp.json()
        expected_true = not any(d["accessionId"] == _first_csv_row_id for d in res["metadataObjects"])
        assert expected_true, f"object {_first_csv_row_id} still exists"

    _filename = "empty.csv"
    # status should be 400
    await post_object_expect_status(sess, _schema, folder_id, _filename, 400)

    _filename = "EGA_sample_w_issue.csv"
    # status should be 201 but we expect 3 rows, as the CSV has 4 rows one of which is empty
    accession_id = await post_object_expect_status(sess, _schema, folder_id, _filename, 201)
    assert len(accession_id[0]) == 3, f"expected nb of CSV entries does not match, we got: {len(accession_id)}"


async def test_put_objects(sess, folder_id):
    """Test PUT reqs.

    Tries to create new object, gets accession id and checks if correct
    resource is returned with that id. Try to use PUT with JSON and expect failure,
    try to use PUT with XML and expect success.

    :param sess: HTTP session in which request call is made
    :param folder_id: id of the folder used to group submission
    """
    accession_id = await post_object(sess, "study", folder_id, "SRP000539.xml")
    await put_object_json(sess, "study", accession_id[0], "SRP000539.json")
    await put_object_xml(sess, "study", accession_id[0], "SRP000539_put.xml")
    await check_folders_object_patch(
        sess,
        folder_id,
        "study",
        accession_id,
        "Highly integrated epigenome maps in Arabidopsis - whole genome shotgun bisulfite sequencing",
        "SRP000539_put.xml",
    )


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
    draft_id = await post_draft_json(sess, schema, folder_id, orginal_file)
    async with sess.get(f"{drafts_url}/{schema}/{draft_id}") as resp:
        assert resp.status == 200, f"HTTP Status code error, got {resp.status}"
        res = await resp.json()
        title = res["descriptor"]["studyTitle"] if schema == "study" else res.get("title", "")
    await check_folders_object_patch(sess, folder_id, draft_id, schema, title, orginal_file, draft=True)

    accession_id = await put_draft(sess, schema, draft_id, update_file)
    async with sess.get(f"{drafts_url}/{schema}/{accession_id}") as resp:
        LOG.debug(f"Checking that {accession_id} JSON is in {schema}")
        assert resp.status == 200, f"HTTP Status code error, got {resp.status}"
        res = await resp.json()
        title = res["descriptor"]["studyTitle"] if schema == "study" else res.get("title", "")
    await check_folders_object_patch(sess, folder_id, schema, accession_id, title, update_file, draft=True)

    await delete_draft(sess, schema, accession_id)
    async with sess.get(f"{drafts_url}/{schema}/{accession_id}") as resp:
        LOG.debug(f"Checking that JSON object {accession_id} was deleted")
        assert resp.status == 404, f"HTTP Status code error, got {resp.status}"

    async with sess.get(f"{folders_url}/{folder_id}") as resp:
        LOG.debug(f"Checking that JSON object {accession_id} was deleted from folder {folder_id}")
        res = await resp.json()
        expected_true = not any(d["accessionId"] == accession_id for d in res["drafts"])
        assert expected_true, f"draft object {accession_id} still exists"


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
    draft_id = await post_draft_json(sess, schema, folder_id, orginal_file)
    accession_id = await patch_draft(sess, schema, draft_id, update_file)
    async with sess.get(f"{drafts_url}/{schema}/{accession_id}") as resp:
        LOG.debug(f"Checking that {accession_id} JSON is in {schema}")
        res = await resp.json()
        title = res["descriptor"]["studyTitle"] if schema == "study" else res.get("title", None)
        assert res["centerName"] == "GEOM", "object centerName content mismatch"
        assert res["alias"] == "GSE10968", "object alias content mismatch"
        assert resp.status == 200, f"HTTP Status code error, got {resp.status}"
    await check_folders_object_patch(sess, folder_id, schema, accession_id, title, update_file, draft=True)

    await delete_draft(sess, schema, accession_id)
    async with sess.get(f"{drafts_url}/{schema}/{accession_id}") as resp:
        LOG.debug(f"Checking that JSON object {accession_id} was deleted")
        assert resp.status == 404, f"HTTP Status code error, got {resp.status}"


async def test_querying_works(sess, folder_id):
    """Test query endpoint with working and failing query.

    :param sess: HTTP session in which request call is made
    :param folder_id: id of the folder used to group submission objects
    """
    files = await asyncio.gather(
        *[post_object(sess, schema, folder_id, filename) for schema, filename in test_xml_files]
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
        async with sess.get(f"{objects_url}/{schema}?{key}={value}") as resp:
            assert resp.status == expected_status, f"HTTP Status code error, got {resp.status}"

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
    files = await asyncio.gather(*[post_object(sess, "study", folder_id, "SRP000539.xml") for _ in range(13)])

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


async def test_metax_crud(sess, folder_id):
    """Test Metax service with study and dataset POST, PATCH, PUBLISH and DELETE reqs.

    :param sess: HTTP session in which request call is made
    :param folder_id: id of the folder where objects reside
    """
    # POST to object endpoint creates draft dataset in Metax for Study and Dataset
    ids = []
    xml_files = set()
    for schema, filename, update_filename in {
        ("study", "SRP000539.xml", "SRP000539_put.xml"),
        ("dataset", "dataset.xml", "dataset_put.xml"),
    }:
        accession_id, _ = await post_object(sess, schema, folder_id, filename)
        xml_files.add((schema, accession_id, update_filename))
        ids.append([schema, accession_id])

    json_files = set()
    for schema, filename, update_filename in {
        ("study", "SRP000539.json", "patch.json"),
        ("dataset", "dataset.json", "dataset_patch.json"),
    }:
        accession_id = await post_object_json(sess, schema, folder_id, filename)
        json_files.add((schema, accession_id, filename, update_filename))
        ids.append([schema, accession_id])

    for object in ids:
        schema, accession_id = object
        async with sess.get(f"{objects_url}/{schema}/{accession_id}") as resp:
            assert resp.status == 200, f"HTTP Status code error, got {resp.status}"
            res = await resp.json()
            try:
                metax_id = res["metaxIdentifier"]["identifier"]
            except KeyError:
                assert False, "Metax ID was not in response data"
        object.append(metax_id)
        async with sess.get(f"{metax_url}/{metax_id}") as metax_resp:
            assert metax_resp.status == 200, f"HTTP Status code error, got {resp.status}"
            metax_res = await metax_resp.json()
            assert (
                res.get("doi", None) == metax_res["research_dataset"]["preferred_identifier"]
            ), "Object's DOI was not in Metax response data preferred_identifier"
            assert metax_res.get("date_modified", None) is None

    # PUT and PATCH to object endpoint updates draft dataset in Metax for Study and Dataset
    for schema, accession_id, filename in xml_files:
        await put_object_xml(sess, schema, accession_id, filename)
    for schema, accession_id, filename, _ in json_files:
        await put_object_json(sess, schema, accession_id, filename)
    for schema, accession_id, _, filename in json_files:
        await patch_object_json(sess, schema, accession_id, filename)

    for _, _, metax_id in ids:
        async with sess.get(f"{metax_url}/{metax_id}") as metax_resp:
            assert metax_resp.status == 200, f"HTTP Status code error, got {resp.status}"
            metax_res = await metax_resp.json()
            assert (
                metax_res.get("date_modified", None) is not None
            ), f"Object with metax id {metax_res['identifier']} was not updated in Metax"

    # DELETE object from Metax
    for schema, accession_id, _ in xml_files:
        await delete_object(sess, schema, accession_id)
    for schema, accession_id, _, _ in json_files:
        await delete_object(sess, schema, accession_id)
    for _, _, metax_id in ids:
        async with sess.get(f"{metax_url}/{metax_id}") as metax_resp:
            assert metax_resp.status == 404, f"HTTP Status code error - expected 404 Not Found, got {resp.status}"


async def test_metax_id_not_updated_on_patch(sess, folder_id):
    """Test that Metax id cannot be sent in patch.

    :param sess: HTTP session in which request call is made
    :param folder_id: id of the folder where objects reside
    """
    for schema, filename in {
        ("study", "SRP000539.json"),
        ("dataset", "dataset.json"),
    }:
        accession_id = await post_object_json(sess, schema, folder_id, filename)
        async with sess.patch(
            f"{objects_url}/{schema}/{accession_id}", data={"metaxIdentifier": {"identifier": "12345"}}
        ) as resp:
            LOG.debug(f"Try to patch object in {schema}")
            assert resp.status == 400


async def test_metax_publish_dataset(sess, folder_id):
    """Test publishing dataset to Metax service after folder(submission) is published.

    :param sess: HTTP session in which request call is made
    :param folder_id: id of the folder where objects reside
    """
    # POST to object endpoint creates draft dataset in Metax for Study and Dataset
    objects = []
    for schema, filename in {
        ("study", "SRP000539.xml"),
        ("dataset", "dataset.xml"),
    }:
        accession_id, _ = await post_object(sess, schema, folder_id, filename)
        objects.append([schema, accession_id])

    for object in objects:
        schema, object_id = object
        async with sess.get(f"{objects_url}/{schema}/{object_id}") as resp:
            assert resp.status == 200, f"HTTP Status code error, got {resp.status}"
            res = await resp.json()
            object.append(res["metaxIdentifier"]["identifier"])

    await publish_folder(sess, folder_id)

    # TODO: This must be updated as Metax identifier will be moved to folder from object after publishing
    # for schema, object_id, metax_id in objects:
    #     async with sess.get(f"{objects_url}/{schema}/{object_id}") as resp:
    #         assert resp.status == 200, f"HTTP Status code error, got {resp.status}"
    #         res = await resp.json()
    #         actual = res["metaxIdentifier"]
    #         expected = {"identifier": metax_id, "status": "published"}
    #         assert expected == actual

    #     async with sess.get(f"{metax_url}/{metax_id}") as metax_resp:
    #         assert metax_resp.status == 200, f"HTTP Status code error, got {resp.status}"
    #         metax_res = await metax_resp.json()
    #         assert metax_res["state"] == "published"


async def test_crud_folders_works(sess):
    """Test folders REST api POST, GET, PATCH, PUBLISH and DELETE reqs.

    :param sess: HTTP session in which request call is made
    """
    # Create new folder and check its creation succeeded
    folder_data = {"name": "Mock Folder", "description": "Mock Base folder to folder ops"}
    folder_id = await post_folder(sess, folder_data)
    async with sess.get(f"{folders_url}/{folder_id}") as resp:
        LOG.debug(f"Checking that folder {folder_id} was created")
        assert resp.status == 200, f"HTTP Status code error, got {resp.status}"

    # Create draft from test XML file and patch the draft into the newly created folder
    draft_id = await post_draft(sess, "sample", folder_id, "SRS001433.xml")
    async with sess.get(f"{folders_url}/{folder_id}") as resp:
        LOG.debug(f"Checking that folder {folder_id} was patched")
        res = await resp.json()
        assert res["folderId"] == folder_id, "expected folder id does not match"
        assert res["name"] == folder_data["name"], "expected folder name does not match"
        assert res["description"] == folder_data["description"], "folder description content mismatch"
        assert res["published"] is False, "folder is published, expected False"
        assert res["drafts"] == [
            {
                "accessionId": draft_id,
                "schema": "draft-sample",
                "tags": {
                    "submissionType": "XML",
                    "displayTitle": "HapMap sample from Homo sapiens",
                    "fileName": "SRS001433.xml",
                },
            }
        ], "folder drafts content mismatch"
        assert res["metadataObjects"] == [], "there are objects in folder, expected empty"

    # Get the draft from the collection within this session and post it to objects collection
    draft_data = await get_draft(sess, "sample", draft_id)
    async with sess.post(f"{objects_url}/sample", params={"folder": folder_id}, data=draft_data) as resp:
        LOG.debug("Adding draft to actual objects")
        assert resp.status == 201, f"HTTP Status code error, got {resp.status}"
        ans = await resp.json()
        assert ans["accessionId"] != draft_id, "draft id does not match expected"
        accession_id = ans["accessionId"]

    async with sess.get(f"{folders_url}/{folder_id}") as resp:
        LOG.debug(f"Checking that folder {folder_id} was patched")
        res = await resp.json()
        assert res["folderId"] == folder_id, "expected folder id does not match"
        assert res["published"] is False, "folder is published, expected False"
        assert "datePublished" not in res.keys()
        assert res["drafts"] == [
            {
                "accessionId": draft_id,
                "schema": "draft-sample",
                "tags": {
                    "submissionType": "XML",
                    "displayTitle": "HapMap sample from Homo sapiens",
                    "fileName": "SRS001433.xml",
                },
            }
        ], "folder drafts content mismatch"
        assert res["metadataObjects"] == [
            {
                "accessionId": accession_id,
                "schema": "sample",
                "tags": {"submissionType": "Form", "displayTitle": "HapMap sample from Homo sapiens"},
            }
        ], "folder metadataObjects content mismatch"

    # Publish the folder
    folder_id = await publish_folder(sess, folder_id)

    await get_draft(sess, "sample", draft_id, 404)  # checking the draft was deleted after publication

    async with sess.get(f"{folders_url}/{folder_id}") as resp:
        LOG.debug(f"Checking that folder {folder_id} was patched")
        res = await resp.json()
        assert res["folderId"] == folder_id, "expected folder id does not match"
        assert res["published"] is True, "folder is not published, expected True"
        assert "datePublished" in res.keys()
        assert "extraInfo" in res.keys()
        assert res["drafts"] == [], "there are drafts in folder, expected empty"
        assert res["metadataObjects"] == [
            {
                "accessionId": accession_id,
                "schema": "sample",
                "tags": {"submissionType": "Form", "displayTitle": "HapMap sample from Homo sapiens"},
            }
        ], "folder metadataObjects content mismatch"

    # Delete folder
    await delete_folder_publish(sess, folder_id)

    async with sess.get(f"{drafts_url}/sample/{draft_id}") as resp:
        LOG.debug(f"Checking that JSON object {accession_id} was deleted")
        assert resp.status == 404, f"HTTP Status code error, got {resp.status}"


async def test_crud_folders_works_no_publish(sess):
    """Test folders REST api POST, GET, PATCH, PUBLISH and DELETE reqs.

    :param sess: HTTP session in which request call is made
    """
    # Create new folder and check its creation succeeded
    folder_data = {"name": "Mock Unpublished folder", "description": "test umpublished folder"}
    folder_id = await post_folder(sess, folder_data)
    async with sess.get(f"{folders_url}/{folder_id}") as resp:
        LOG.debug(f"Checking that folder {folder_id} was created")
        assert resp.status == 200, f"HTTP Status code error, got {resp.status}"

    # Create draft from test XML file and patch the draft into the newly created folder
    draft_id = await post_draft(sess, "sample", folder_id, "SRS001433.xml")
    async with sess.get(f"{folders_url}/{folder_id}") as resp:
        LOG.debug(f"Checking that folder {folder_id} was patched")
        res = await resp.json()
        assert res["folderId"] == folder_id, "expected folder id does not match"
        assert res["name"] == folder_data["name"], "expected folder name does not match"
        assert res["description"] == folder_data["description"], "folder description content mismatch"
        assert res["published"] is False, "folder is published, expected False"
        assert res["drafts"] == [
            {
                "accessionId": draft_id,
                "schema": "draft-sample",
                "tags": {
                    "submissionType": "XML",
                    "displayTitle": "HapMap sample from Homo sapiens",
                    "fileName": "SRS001433.xml",
                },
            }
        ], "folder drafts content mismatch"
        assert res["metadataObjects"] == [], "there are objects in folder, expected empty"

    # Get the draft from the collection within this session and post it to objects collection
    draft = await get_draft(sess, "sample", draft_id)
    async with sess.post(f"{objects_url}/sample", params={"folder": folder_id}, data=draft) as resp:
        LOG.debug("Adding draft to actual objects")
        assert resp.status == 201, f"HTTP Status code error, got {resp.status}"
        ans = await resp.json()
        assert ans["accessionId"] != draft_id, "draft id does not match expected"
        accession_id = ans["accessionId"]

    async with sess.get(f"{folders_url}/{folder_id}") as resp:
        LOG.debug(f"Checking that folder {folder_id} was patched")
        res = await resp.json()
        assert res["folderId"] == folder_id, "expected folder id does not match"
        assert res["published"] is False, "folder is published, expected False"
        assert res["drafts"] == [
            {
                "accessionId": draft_id,
                "schema": "draft-sample",
                "tags": {
                    "submissionType": "XML",
                    "displayTitle": "HapMap sample from Homo sapiens",
                    "fileName": "SRS001433.xml",
                },
            }
        ], "folder drafts content mismatch"
        assert res["metadataObjects"] == [
            {
                "accessionId": accession_id,
                "schema": "sample",
                "tags": {"submissionType": "Form", "displayTitle": "HapMap sample from Homo sapiens"},
            }
        ], "folder metadataObjects content mismatch"

    # Delete folder
    await delete_folder(sess, folder_id)
    async with sess.get(f"{folders_url}/{folder_id}") as resp:
        LOG.debug(f"Checking that folder {folder_id} was deleted")
        assert resp.status == 404, f"HTTP Status code error, got {resp.status}"

    async with sess.get(f"{users_url}/current") as resp:
        LOG.debug(f"Checking that folder {folder_id} was deleted from current user")
        res = await resp.json()
        expected_true = not any(d == accession_id for d in res["folders"])
        assert expected_true, "folder still exists at user"


async def test_adding_doi_info_to_folder_works(sess):
    """Test that proper DOI info can be added to folder and bad DOI info cannot be.

    :param sess: HTTP session in which request call is made
    """
    # Create new folder and check its creation succeeded
    folder_data = {"name": "DOI Folder", "description": "Mock Base folder for adding DOI info"}
    folder_id = await post_folder(sess, folder_data)
    async with sess.get(f"{folders_url}/{folder_id}") as resp:
        LOG.debug(f"Checking that folder {folder_id} was created")
        assert resp.status == 200, f"HTTP Status code error, got {resp.status}"

    # Get correctly formatted DOI info and patch it into the new folder successfully
    doi_data_raw = await create_request_json_data("doi", "test_doi.json")
    doi_data = json.loads(doi_data_raw)
    patch_add_doi = [{"op": "add", "path": "/doiInfo", "value": doi_data}]
    folder_id = await patch_folder(sess, folder_id, patch_add_doi)

    async with sess.get(f"{folders_url}/{folder_id}") as resp:
        LOG.debug(f"Checking that folder {folder_id} was patched")
        res = await resp.json()
        assert res["folderId"] == folder_id, "expected folder id does not match"
        assert res["name"] == folder_data["name"], "expected folder name does not match"
        assert res["description"] == folder_data["description"], "folder description content mismatch"
        assert res["published"] is False, "folder is published, expected False"
        assert res["doiInfo"] == doi_data, "folder doi does not match"

    # Test that an incomplete DOI object fails to patch into the folder
    patch_add_bad_doi = [{"op": "add", "path": "/doiInfo", "value": {"identifier": {}}}]
    async with sess.patch(f"{folders_url}/{folder_id}", data=json.dumps(patch_add_bad_doi)) as resp:
        LOG.debug(f"Tried updating folder {folder_id}")
        assert resp.status == 400, f"HTTP Status code error, got {resp.status}"
        res = await resp.json()
        assert res["detail"] == "Provided input does not seem correct for field: 'doiInfo'", "expected error mismatch"

    # Check the existing DOI info is not altered
    async with sess.get(f"{folders_url}/{folder_id}") as resp:
        LOG.debug(f"Checking that folder {folder_id} was not patched with bad DOI")
        res = await resp.json()
        assert res["doiInfo"] == doi_data, "folder doi does not match"

    # Test that extraInfo cannot be altered
    patch_add_bad_doi = [{"op": "add", "path": "/extraInfo", "value": {"publisher": "something"}}]
    async with sess.patch(f"{folders_url}/{folder_id}", data=json.dumps(patch_add_bad_doi)) as resp:
        LOG.debug(f"Tried updating folder {folder_id}")
        assert resp.status == 400, f"HTTP Status code error, got {resp.status}"
        res = await resp.json()
        assert res["detail"] == "Request contains '/extraInfo' key that cannot be updated to folders.", "error mismatch"

    # Delete folder
    await delete_folder(sess, folder_id)
    async with sess.get(f"{folders_url}/{folder_id}") as resp:
        LOG.debug(f"Checking that folder {folder_id} was deleted")
        assert resp.status == 404, f"HTTP Status code error, got {resp.status}"


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


async def test_getting_folders_filtered_by_name(sess):
    """Check that /folders returns folders filtered by name.

    :param sess: HTTP session in which request call is made
    """
    names = [" filter new ", "_filter_", "-filter-", "_extra-", "_2021special_"]
    folders = []
    for name in names:
        folder_data = {"name": f"Test{name}name", "description": "Test filtering name"}
        folders.append(await post_folder(sess, folder_data))

    async with sess.get(f"{folders_url}?name=filter") as resp:
        ans = await resp.json()
        assert resp.status == 200, f"HTTP Status code error {resp.status} {ans}"
        assert ans["page"]["totalFolders"] == 3, f'Shold be 3 returned {ans["page"]["totalFolders"]}'

    async with sess.get(f"{folders_url}?name=extra") as resp:
        ans = await resp.json()
        assert resp.status == 200, f"HTTP Status code error {resp.status} {ans}"
        assert ans["page"]["totalFolders"] == 1

    async with sess.get(f"{folders_url}?name=2021 special") as resp:
        assert resp.status == 200
        ans = await resp.json()
        assert ans["page"]["totalFolders"] == 0

    async with sess.get(f"{folders_url}?name=new extra") as resp:
        assert resp.status == 200
        ans = await resp.json()
        assert ans["page"]["totalFolders"] == 2

    for folder in folders:
        await delete_folder(sess, folder)


async def test_getting_folders_filtered_by_date_created(sess):
    """Check that /folders returns folders filtered by date created.

    :param sess: HTTP session in which request call is made
    """
    async with sess.get(f"{users_url}/current") as resp:
        ans = await resp.json()
        user = ans["userId"]

    folders = []
    format = "%Y-%m-%d %H:%M:%S"

    # Test dateCreated within a year
    # Create folders with different dateCreated
    timestamps = ["2014-12-31 00:00:00", "2015-01-01 00:00:00", "2015-07-15 00:00:00", "2016-01-01 00:00:00"]
    for stamp in timestamps:
        folder_data = {
            "name": f"Test date {stamp}",
            "description": "Test filtering date",
            "dateCreated": datetime.strptime(stamp, format).timestamp(),
        }
        folders.append(await create_folder(folder_data, user))

    async with sess.get(f"{folders_url}?date_created_start=2015-01-01&date_created_end=2015-12-31") as resp:
        ans = await resp.json()
        assert resp.status == 200, f"returned status {resp.status}, error {ans}"
        assert ans["page"]["totalFolders"] == 2, f'Shold be 2 returned {ans["page"]["totalFolders"]}'

    # Test dateCreated within a month
    # Create folders with different dateCreated
    timestamps = ["2013-01-31 00:00:00", "2013-02-02 00:00:00", "2013-03-29 00:00:00", "2013-04-01 00:00:00"]
    for stamp in timestamps:
        folder_data = {
            "name": f"Test date {stamp}",
            "description": "Test filtering date",
            "dateCreated": datetime.strptime(stamp, format).timestamp(),
        }
        folders.append(await create_folder(folder_data, user))

    async with sess.get(f"{folders_url}?date_created_start=2013-02-01&date_created_end=2013-03-30") as resp:
        ans = await resp.json()
        assert resp.status == 200, f"returned status {resp.status}, error {ans}"
        assert ans["page"]["totalFolders"] == 2, f'Shold be 2 returned {ans["page"]["totalFolders"]}'

    # Test dateCreated within a day
    # Create folders with different dateCreated
    timestamps = [
        "2012-01-14 23:59:59",
        "2012-01-15 00:00:01",
        "2012-01-15 23:59:59",
        "2012-01-16 00:00:01",
    ]
    for stamp in timestamps:
        folder_data = {
            "name": f"Test date {stamp}",
            "description": "Test filtering date",
            "dateCreated": datetime.strptime(stamp, format).timestamp(),
        }
        folders.append(await create_folder(folder_data, user))

    async with sess.get(f"{folders_url}?date_created_start=2012-01-15&date_created_end=2012-01-15") as resp:
        ans = await resp.json()
        assert resp.status == 200, f"returned status {resp.status}, error {ans}"
        assert ans["page"]["totalFolders"] == 2, f'Shold be 2 returned {ans["page"]["totalFolders"]}'

    # Test parameters date_created_... and name together
    async with sess.get(f"{folders_url}?name=2013&date_created_start=2012-01-01&date_created_end=2016-12-31") as resp:
        ans = await resp.json()
        assert resp.status == 200, f"returned status {resp.status}, error {ans}"
        assert ans["page"]["totalFolders"] == 4, f'Shold be 4 returned {ans["page"]["totalFolders"]}'

    for folder in folders:
        await delete_folder(sess, folder)


async def test_getting_user_items(sess):
    """Test querying user's templates or folders in the user object with GET user request.

    :param sess: HTTP session in which request call is made
    """
    # Get real user ID
    async with sess.get(f"{users_url}/{user_id}") as resp:
        LOG.debug(f"Reading user {user_id}")
        assert resp.status == 200, f"HTTP Status code error, got {resp.status}"

    # Add template to user
    template_id = await post_template_json(sess, "study", "SRP000539_template.json")

    # Test querying for list of user draft templates
    async with sess.get(f"{users_url}/{user_id}?items=templates") as resp:
        LOG.debug(f"Reading user {user_id} templates")
        assert resp.status == 200, f"HTTP Status code error, got {resp.status}"
        ans = await resp.json()
        assert ans["page"]["page"] == 1
        assert ans["page"]["size"] == 5
        assert ans["page"]["totalPages"] == 1
        assert ans["page"]["totalTemplates"] == 1
        assert len(ans["templates"]) == 1

    async with sess.get(f"{users_url}/{user_id}?items=templates&per_page=3") as resp:
        LOG.debug(f"Reading user {user_id} templates")
        assert resp.status == 200, f"HTTP Status code error, got {resp.status}"
        ans = await resp.json()
        assert ans["page"]["page"] == 1
        assert ans["page"]["size"] == 3
        assert len(ans["templates"]) == 1

    await delete_template(sess, "study", template_id)  # Future tests will assume the templates key is empty

    # Test querying for the list of folder IDs
    async with sess.get(f"{users_url}/{user_id}?items=folders") as resp:
        LOG.debug(f"Reading user {user_id} folder list")
        assert resp.status == 200, f"HTTP Status code error, got {resp.status}"
        ans = await resp.json()
        assert ans["page"]["page"] == 1
        assert ans["page"]["size"] == 5
        assert ans["page"]["totalPages"] == 2
        assert ans["page"]["totalFolders"] == 6
        assert len(ans["folders"]) == 5

    # Test the same with a bad query param
    async with sess.get(f"{users_url}/{user_id}?items=bad") as resp:
        LOG.debug(f"Reading user {user_id} but with faulty item descriptor")
        assert resp.status == 400, f"HTTP Status code error, got {resp.status}"


async def test_crud_users_works(sess):
    """Test users REST api GET, PATCH and DELETE reqs.

    :param sess: HTTP session in which request call is made
    """
    # Check user exists in database (requires an user object to be mocked)
    async with sess.get(f"{users_url}/{user_id}") as resp:
        LOG.debug(f"Reading user {user_id}")
        assert resp.status == 200, f"HTTP Status code error, got {resp.status}"
        response = await resp.json()
        real_user_id = response["userId"]

    # Add user to session and create a patch to add folder to user
    folder_not_published = {"name": "Mock User Folder", "description": "Mock folder for testing users"}
    folder_id = await post_folder(sess, folder_not_published)

    async with sess.get(f"{users_url}/{user_id}") as resp:
        LOG.debug(f"Checking that folder {folder_id} was added")
        res = await resp.json()
        assert res["userId"] == real_user_id, "user id does not match"
        assert res["name"] == f"{test_user_given} {test_user_family}", "user name mismatch"
        assert res["templates"] == [], "user templates content mismatch"
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

    template_id = await post_template_json(sess, "study", "SRP000539_template.json")
    await patch_template(sess, "study", template_id, "patch.json")
    async with sess.get(f"{users_url}/{user_id}") as resp:
        LOG.debug(f"Checking that template: {template_id} was added")
        res = await resp.json()
        assert res["templates"][0]["accessionId"] == template_id, "added template does not exists"
        assert "tags" not in res["templates"][0]

    patch_change_tags_object = [
        {
            "op": "add",
            "path": "/templates/0/tags",
            "value": {"displayTitle": "Test"},
        }
    ]
    await patch_user(sess, user_id, real_user_id, patch_change_tags_object)

    async with sess.get(f"{users_url}/{user_id}") as resp:
        LOG.debug(f"Checking that template: {template_id} was added")
        res = await resp.json()
        assert res["templates"][0]["accessionId"] == template_id, "added template does not exists"
        assert res["templates"][0]["tags"]["displayTitle"] == "Test"

    await delete_template(sess, "study", template_id)

    async with sess.get(f"{users_url}/{user_id}") as resp:
        LOG.debug(f"Checking that template {template_id} was added")
        res = await resp.json()
        assert len(res["templates"]) == 0, "template was not deleted from users"

    template_ids = await post_template_json(sess, "study", "SRP000539_list.json")
    assert len(template_ids) == 2, "templates could not be added as batch"

    async with sess.get(f"{users_url}/{user_id}") as resp:
        LOG.debug(f"Checking that template {template_id} was added")
        res = await resp.json()
        assert res["templates"][1]["tags"]["submissionType"] == "Form"

    # Delete user
    await delete_user(sess, user_id)
    # 401 means API is innacessible thus session ended
    # this check is not needed but good to do
    async with sess.get(f"{users_url}/{user_id}") as resp:
        LOG.debug(f"Checking that user {user_id} was deleted")
        assert resp.status == 401, f"HTTP Status code error, got {resp.status}"


async def test_get_folders(sess, folder_id: str):
    """Test folders REST api GET .

    :param sess: HTTP session in which request call is made
    :param folder_id: id of the folder used to group submission objects
    """
    async with sess.get(f"{folders_url}") as resp:
        LOG.debug(f"Reading folder {folder_id}")
        assert resp.status == 200, f"HTTP Status code error, got {resp.status}"
        response = await resp.json()
        assert len(response["folders"]) == 1
        assert response["page"] == {"page": 1, "size": 5, "totalPages": 1, "totalFolders": 1}
        assert response["folders"][0]["folderId"] == folder_id


async def test_get_folders_objects(sess, folder_id: str):
    """Test folders REST api GET with objects.

    :param sess: HTTP session in which request call is made
    :param folder_id: id of the folder used to group submission objects
    """
    accession_id = await post_object_json(sess, "study", folder_id, "SRP000539.json")
    async with sess.get(f"{folders_url}") as resp:
        LOG.debug(f"Reading folder {folder_id}")
        assert resp.status == 200, f"HTTP Status code error, got {resp.status}"
        response = await resp.json()
        assert len(response["folders"]) == 1
        assert response["folders"][0]["metadataObjects"][0]["accessionId"] == accession_id
        assert "tags" in response["folders"][0]["metadataObjects"][0]
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
        assert resp.status == 200, f"HTTP Status code error, got {resp.status}"
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
        assert resp.status == 200, f"HTTP Status code error, got {resp.status}"
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
        assert resp.status == 200, f"HTTP Status code error, got {resp.status}"
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
        assert resp.status == 200, f"HTTP Status code error, got {resp.status}"
        res = await resp.json()
        assert len(res) == 2, "expected 2 objects"
        new_study_access_id = res[0]["accessionId"]
        assert study_access_id == new_study_access_id

    # Check the modified object was inserted correctly
    async with sess.get(f"{objects_url}/study/{new_study_access_id}") as resp:
        LOG.debug("Checking that previous object was modified correctly")
        assert resp.status == 200, f"HTTP Status code error, got {resp.status}"
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
        assert resp.status == 200, f"HTTP Status code error, got {resp.status}"
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

        # test XML files
        await asyncio.gather(*[test_crud_works(sess, schema, file, basic_folder_id) for schema, file in test_xml_files])

        # test CSV files
        await test_csv(sess, basic_folder_id)

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
        await test_adding_doi_info_to_folder_works(sess)

        # Test getting a list of folders and draft templates owned by the user
        LOG.debug("=== Testing getting folders, draft folders and draft templates with pagination ===")
        await test_getting_paginated_folders(sess)
        await test_getting_user_items(sess)
        LOG.debug("=== Testing getting folders filtered with name and date created ===")
        await test_getting_folders_filtered_by_name(sess)
        # too much of a hassle to make test work with tls db connection in github
        # must be improven in next integration test iteration
        if not TLS:
            await test_getting_folders_filtered_by_date_created(sess)

        # Test objects study and dataset are connecting to metax and saving metax id to db
        LOG.debug("=== Testing Metax integration related basic CRUD operations for study and dataset ===")
        metax_folder = {
            "name": "basic test pagination",
            "description": "basic test pagination folder",
        }
        metax_folder_id = await post_folder(sess, metax_folder)
        await test_metax_crud(sess, metax_folder_id)
        await test_metax_id_not_updated_on_patch(sess, metax_folder_id)
        await test_metax_publish_dataset(sess, metax_folder_id)

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
            assert resp.status == 200, f"HTTP Status code error, got {resp.status}"
            response = await resp.json()
            real_user_id = response["userId"]
        await delete_user(sess, real_user_id)


if __name__ == "__main__":
    asyncio.run(main())
