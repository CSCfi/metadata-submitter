"""
Run integration tests against backend API endpoints.

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
from mongo import Mongo

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
    ("image", "images_single.xml"),
    ("bpdataset", "template_dataset.xml"),
]
test_json_files = [
    ("study", "SRP000539.json", "SRP000539.json"),
    ("sample", "SRS001433.json", "SRS001433.json"),
    ("dataset", "dataset.json", "dataset.json"),
    ("run", "ERR000076.json", "ERR000076.json"),
    ("experiment", "ERX000119.json", "ERX000119.json"),
    ("analysis", "ERZ266973.json", "ERZ266973.json"),
]
API_PREFIX = "/v1"
base_url = os.getenv("BASE_URL", "http://localhost:5430")
mock_auth_url = os.getenv("OIDC_URL_TEST", "http://localhost:8000")
objects_url = f"{base_url}{API_PREFIX}/objects"
drafts_url = f"{base_url}{API_PREFIX}/drafts"
templates_url = f"{base_url}{API_PREFIX}/templates"
submissions_url = f"{base_url}{API_PREFIX}/submissions"
users_url = f"{base_url}{API_PREFIX}/users"
submit_url = f"{base_url}{API_PREFIX}/submit"
publish_url = f"{base_url}{API_PREFIX}/publish"
metax_url = f"{os.getenv('METAX_URL', 'http://localhost:8002')}/rest/v2/datasets"
datacite_url = f"{os.getenv('DOI_API', 'http://localhost:8001/dois')}"
auth = aiohttp.BasicAuth(os.getenv("METAX_USER", "sd"), os.getenv("METAX_PASS", "test"))
# to form direct contact to db with eg create_submission()
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


async def get_user_data(sess):
    """Get current logged in user's data model.

    :param sess: HTTP session in which request call is made
    """
    async with sess.get(f"{users_url}/current") as resp:
        LOG.debug("Get userdata")
        ans = await resp.json()
        assert resp.status == 200, f"HTTP Status code error {resp.status} {ans}"
        return ans


async def create_request_data(schema, filename):
    """Create request data from pairs of schemas and filenames.

    :param schema: name of the schema (submission) used for testing
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

    :param schema: name of the schema (submission) used for testing
    :param filename: name of the file used for testing.
    """
    path_to_file = testfiles_root / schema / filename
    path = path_to_file.as_posix()
    async with aiofiles.open(path, mode="r") as f:
        request_data = await f.read()
    return request_data


async def get_object(sess, schema, accession_id):
    """Get one metadata object within session, returns object's data.

    :param sess: HTTP session in which request call is made
    :param schema: name of the schema (submission) used for testing
    :param accession_id: object to fetch
    :return: data of an object
    """
    async with sess.get(f"{objects_url}/{schema}/{accession_id}") as resp:
        LOG.debug(f"Getting object from {schema} with {accession_id}")
        assert resp.status == 200, f"HTTP Status code error, got {resp.status}"
        data = await resp.json()
        return data


async def post_object(sess, schema, submission_id, filename):
    """Post one metadata object within session, returns accessionId.

    :param sess: HTTP session in which request call is made
    :param schema: name of the schema (submission) used for testing
    :submission_id: submission object belongs to
    :param filename: name of the file used for testing.
    :return: accessionId of created object
    """
    request_data = await create_request_data(schema, filename)
    async with sess.post(f"{objects_url}/{schema}", params={"submission": submission_id}, data=request_data) as resp:
        LOG.debug(f"Adding new object to {schema}, via XML/CSV file {filename}")
        assert resp.status == 201, f"HTTP Status code error, got {resp.status}"
        ans = await resp.json()
        return ans if isinstance(ans, list) else ans["accessionId"], schema


async def post_multi_object(sess, schema, submission_id, filename):
    """Post metadata objects from one file within session, returns response body (json).

    :param sess: HTTP session in which request call is made
    :param schema: name of the schema (submission) used for testing
    :submission_id: submission object belongs to
    :param filename: name of the file used for testing.
    :return: response data after created objects
    """
    request_data = await create_request_data(schema, filename)
    async with sess.post(f"{objects_url}/{schema}", params={"submission": submission_id}, data=request_data) as resp:
        LOG.debug(f"Adding new object to {schema}, via XML/CSV file {filename}")
        assert resp.status == 201, f"HTTP Status code error, got {resp.status}"
        return await resp.json()


async def post_object_expect_status(sess, schema, submission_id, filename, status):
    """Post one metadata object within session, returns accessionId.

    :param sess: HTTP session in which request call is made
    :param schema: name of the schema (submission) used for testing
    :submission_id: submission object belongs to
    :param filename: name of the file used for testing
    :param: HTTP status to expect for
    :return: accessionId of created object
    """
    request_data = await create_request_data(schema, filename)
    async with sess.post(f"{objects_url}/{schema}", params={"submission": submission_id}, data=request_data) as resp:
        LOG.debug(f"Adding new object to {schema}, via XML/CSV file {filename} and expecting status: {status}")
        assert resp.status == status, f"HTTP Status code error, got {resp.status}"
        if status < 400:
            ans = await resp.json()
            return ans if isinstance(ans, list) else ans["accessionId"], schema


async def post_object_json(sess, schema, submission_id, filename):
    """Post & put one metadata object within session, returns accessionId.

    :param sess: HTTP session in which request call is made
    :param schema: name of the schema (submission) used for testing
    :submission_id: submission object belongs to
    :param filename: name of the file used for testing.
    :return: accessionId of created object
    """
    request_data = await create_request_json_data(schema, filename)
    async with sess.post(f"{objects_url}/{schema}", params={"submission": submission_id}, data=request_data) as resp:
        LOG.debug(f"Adding new object to {schema}, via JSON file {filename}")
        assert resp.status == 201, f"HTTP Status code error, got {resp.status}"
        ans = await resp.json()
        return ans["accessionId"]


async def delete_object(sess, schema, accession_id):
    """Delete metadata object within session.

    :param sess: HTTP session in which request call is made
    :param schema: name of the schema (submission) used for testing
    :param accession_id: id of the object
    """
    async with sess.delete(f"{objects_url}/{schema}/{accession_id}") as resp:
        LOG.debug(f"Deleting object {accession_id} from {schema}")
        assert resp.status == 204, f"HTTP Status code error, got {resp.status}"


async def post_draft(sess, schema, submission_id, filename):
    """Post one draft metadata object within session, returns accessionId.

    :param sess: HTTP session in which request call is made
    :param schema: name of the schema (submission) used for testing
    :submission_id: submission object belongs to
    :param filename: name of the file used for testing.
    :return: accessionId of created draft
    """
    request_data = await create_request_data(schema, filename)
    async with sess.post(f"{drafts_url}/{schema}", params={"submission": submission_id}, data=request_data) as resp:
        LOG.debug(f"Adding new draft object to {schema}, via XML file {filename}")
        assert resp.status == 201, f"HTTP Status code error, got {resp.status}"
        ans = await resp.json()
        return ans["accessionId"]


async def post_draft_json(sess, schema, submission_id, filename):
    """Post & put one metadata object within session, returns accessionId.

    :param sess: HTTP session in which request call is made
    :param schema: name of the schema (submission) used for testing
    :submission_id: submission object belongs to
    :param filename: name of the file used for testing.
    :return: accessionId of created draft
    """
    request_data = await create_request_json_data(schema, filename)
    async with sess.post(f"{drafts_url}/{schema}", params={"submission": submission_id}, data=request_data) as resp:
        LOG.debug(f"Adding new draft object to {schema}, via JSON file {filename}")
        ans = await resp.json()
        assert resp.status == 201, f"HTTP Status code error, got {resp.status}: {ans}"
        return ans["accessionId"]


async def get_draft(sess, schema, draft_id, expected_status=200):
    """Get and return a drafted metadata object.

    :param sess: HTTP session in which request call is made
    :param schema: name of the schema (submission) used for testing
    :param draft_id: id of the draft
    :param expected_status: HTTP status to expect for
    :return: data of a draft
    """
    async with sess.get(f"{drafts_url}/{schema}/{draft_id}") as resp:
        LOG.debug(f"Checking that {draft_id} JSON exists")
        assert resp.status == expected_status, f"HTTP Status code error, got {resp.status}"
        ans = await resp.json()
        return json.dumps(ans)


async def put_draft(sess, schema, draft_id, update_filename):
    """Put one metadata object within session, returns accessionId.

    :param sess: HTTP session in which request call is made
    :param schema: name of the schema (submission) used for testing
    :param draft_id: id of the draft
    :param update_filename: name of the file used to use for updating data.
    :return: assession id of updated draft
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
    :param schema: name of the schema (submission) used for testing
    :param accession_id: id of the object
    :param update_filename: name of the file used to use for updating data.
    :return: assession id of updated object
    """
    request_data = await create_request_json_data(schema, update_filename)
    async with sess.put(f"{objects_url}/{schema}/{accession_id}", data=request_data) as resp:
        LOG.debug(f"Try to replace object in {schema}")
        assert resp.status == 415, f"HTTP Status code error, got {resp.status}"


async def patch_object_json(sess, schema, accession_id, update_filename):
    """Patch one metadata object within session, returns accessionId.

    :param sess: HTTP session in which request call is made
    :param schema: name of the schema (submission) used for testing
    :param accession_id: id of the object
    :param update_filename: name of the file used to use for updating data.
    :return: assession id of updated object
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
    :param schema: name of the schema (submission) used for testing
    :param accession_id: id of the object
    :param update_filename: name of the file used to use for updating data.
    :return: assession id of updated object
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
    :param schema: name of the schema (submission) used for testing
    :param draft_id: id of the draft
    :param update_filename: name of the file used to use for updating data.
    :return: assession id of updated draft
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
    :param schema: name of the schema (submission) used for testing
    :param draft_id: id of the draft
    """
    async with sess.delete(f"{drafts_url}/{schema}/{draft_id}") as resp:
        LOG.debug(f"Deleting draft object {draft_id} from {schema}")
        assert resp.status == 204, f"HTTP Status code error, got {resp.status}"


async def post_template_json(sess, schema, filename, project_id):
    """Post one metadata object within session, returns accessionId.

    :param sess: HTTP session in which request call is made
    :param schema: name of the schema (submission) used for testing
    :param filename: name of the file used for testing.
    :param project_id: id of the project the template belongs to
    """
    request_data = await create_request_json_data(schema, filename)
    request_data = json.loads(request_data)
    if type(request_data) is list:
        for rd in request_data:
            rd["projectId"] = project_id
    else:
        request_data["projectId"] = project_id
    request_data = json.dumps(request_data)
    async with sess.post(f"{templates_url}/{schema}", data=request_data) as resp:
        LOG.debug(f"Adding new template object to {schema}, via JSON file {filename}")
        ans = await resp.json()
        assert resp.status == 201, f"HTTP Status code error, got {resp.status}"
        if isinstance(ans, list):
            return ans
        else:
            return ans["accessionId"]


async def get_templates(sess, project_id):
    """Get templates from project.

    :param sess: HTTP session in which request call is made
    :param project_id: id of the project the template belongs to
    """
    async with sess.get(f"{templates_url}?projectId={project_id}") as resp:
        LOG.debug(f"Requesting templates from project={project_id}")
        assert resp.status == 200, f"HTTP Status code error, got {resp.status}"
        ans = await resp.json()
        LOG.debug(f"Received {len(ans)} templates")
        return ans


async def get_template(sess, schema, template_id):
    """Get and return a drafted metadata object.

    :param sess: HTTP session in which request call is made
    :param schema: name of the schema (submission) used for testing
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
    :param schema: name of the schema (submission) used for testing
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
    :param schema: name of the schema (submission) used for testing
    :param template_id: id of the draft
    """
    async with sess.delete(f"{templates_url}/{schema}/{template_id}") as resp:
        LOG.debug(f"Deleting template object {template_id} from {schema}")
        assert resp.status == 204, f"HTTP Status code error, got {resp.status}"


async def post_submission(sess, data):
    """Post one object submission within session, returns submissionId.

    :param sess: HTTP session in which request call is made
    :param data: data used to update the submission
    """
    async with sess.post(f"{submissions_url}", data=json.dumps(data)) as resp:
        ans = await resp.json()
        assert resp.status == 201, f"HTTP Status code error {resp.status} {ans}"
        LOG.debug(f"Adding new submission {ans['submissionId']}")
        return ans["submissionId"]


async def patch_submission(sess, submission_id, data):
    """Patch one object submission within session, return submissionId.

    :param sess: HTTP session in which request call is made
    :param submission_id: id of the submission
    :param data: JSON object to use in PATCH call
    """
    async with sess.patch(f"{submissions_url}/{submission_id}", data=json.dumps(data)) as resp:
        LOG.debug(f"Updating submission {submission_id}")
        assert resp.status == 200, f"HTTP Status code error, got {resp.status}"
        ans_patch = await resp.json()
        assert ans_patch["submissionId"] == submission_id, "submission ID error"
        return ans_patch["submissionId"]


async def publish_submission(sess, submission_id):
    """Publish one object submission within session, return submissionId.

    :param sess: HTTP session in which request call is made
    :param submission_id: id of the submission
    """
    async with sess.patch(f"{publish_url}/{submission_id}") as resp:
        LOG.debug(f"Publishing submission {submission_id}")
        ans = await resp.json()
        assert resp.status == 200, f"HTTP Status code error, got {resp.status}: {ans}"
        assert ans["submissionId"] == submission_id, "submission ID error"
        return ans["submissionId"]


async def delete_submission(sess, submission_id):
    """Delete object submission within session.

    :param sess: HTTP session in which request call is made
    :param submission_id: id of the submission
    """
    async with sess.delete(f"{submissions_url}/{submission_id}") as resp:
        LOG.debug(f"Deleting submission {submission_id}")
        assert resp.status == 204, f"HTTP Status code error, got {resp.status}"


async def delete_submission_publish(sess, submission_id):
    """Delete object submission within session.

    :param sess: HTTP session in which request call is made
    :param submission_id: id of the submission
    """
    async with sess.delete(f"{submissions_url}/{submission_id}") as resp:
        LOG.debug(f"Deleting submission {submission_id}")
        assert resp.status == 401, f"HTTP Status code error, got {resp.status}"


async def put_submission_doi(sess, submission_id, data):
    """Put doi into submission within session, returns submissionId.

    :param sess: HTTP session in which request call is made
    :param submission_id: id of the submission
    :param data: doi data used to update the submission
    :returns: Submission id for the submission inserted to database
    """
    async with sess.put(f"{submissions_url}/{submission_id}/doi", data=data) as resp:
        ans = await resp.json()
        assert resp.status == 200, f"HTTP Status code error {resp.status} {ans}"
        LOG.debug(f"Adding doi to submission {ans['submissionId']}")
        return ans["submissionId"]


async def put_submission_dac(sess, submission_id, data):
    """Put DAC into submission within session, returns submissionId.

    :param sess: HTTP session in which request call is made
    :param submission_id: id of the submission
    :param data: dac data used to update the submission
    :returns: Submission id for the submission inserted to database
    """
    async with sess.put(f"{submissions_url}/{submission_id}/dac", data=data) as resp:
        ans = await resp.json()
        assert resp.status == 200, f"HTTP Status code error {resp.status} {ans}"
        LOG.debug(f"Adding DAC to submission {ans['submissionId']}")
        return ans["submissionId"]


async def create_submission(database, data):
    """Create new object submission to database.

    :param database: database client to perform db operations
    :param data: Data as dict to be saved to database
    :returns: Submission id for the submission inserted to database
    """
    submission_id = uuid4().hex
    LOG.info(f"Creating new submission {submission_id}")
    data["submissionId"] = submission_id
    data["text_name"] = " ".join(re.split("[\\W_]", data["name"]))
    data["drafts"] = []
    data["metadataObjects"] = []
    try:
        await database["submission"].insert_one(data)
        return submission_id

    except Exception as e:
        LOG.error(f"Submission creation failed due to {str(e)}")


async def delete_objects_metax_id(sess, database, collection, accession_id, metax_id):
    """Remove study or dataset metax ID from database and mocked Metax service.

    :param sess: HTTP session in which request call is made
    :param database: database client to perform db operations
    :param collection: Collection of the object to be manipulated
    :param accession_id: Accession id of the object to be manipulated
    :param metax_id: ID of metax dataset to be deleted
    """
    try:
        await database[collection].find_one_and_update({"accessionId": accession_id}, {"$set": {"metaxIdentifier": ""}})
    except Exception as e:
        LOG.error(f"Object update failed due to {str(e)}")
    try:
        await sess.delete(f"{metax_url}/{metax_id}")
    except Exception as e:
        LOG.error(f"Object deletion from mmocked Metax failed due to {str(e)}")


async def delete_user(sess, user_id):
    """Delete user object within session.

    :param sess: HTTP session in which request call is made
    :param user_id: id of the user (current)
    """
    async with sess.delete(f"{users_url}/{user_id}") as resp:
        LOG.debug(f"Deleting user {user_id} {await resp.text()}")
        assert resp.status == 204, f"HTTP Status code error, got {resp.status}"


def extract_submissions_object(res, accession_id, draft):
    """Extract object from submission metadataObjects with provided accessionId.

    :param res: JSON parsed responce from submission query request
    :param accession_id: accession ID of reviwed object
    :returns: dict of object entry in submission
    """
    object = "drafts" if draft else "metadataObjects"
    actual_res = next(obj for obj in res[object] if obj["accessionId"] == accession_id)
    return actual_res


async def check_submissions_object_patch(sess, submission_id, schema, accession_id, title, filename, draft=False):
    """Check that draft is added correctly to submission.

    Get draft or metadata object from the submission and assert with data
    returned from object endpoint itself.

    :param sess: HTTP session in which request call is made
    :param submission_id: id of the submission
    :param schema: name of the schema (submission) used for testing
    :param accession_id: accession ID of reviwed object
    :param title: title of reviwed object
    :param filename: name of the file used for inserting data
    :param draft: indication of object draft status, default False
    """
    sub_type = "Form" if filename.split(".")[-1] == "json" else filename.split(".")[-1].upper()
    async with sess.get(f"{submissions_url}/{submission_id}") as resp:
        res = await resp.json()
        try:
            actual = extract_submissions_object(res, accession_id, draft)
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
async def test_crud_works(sess, schema, filename, submission_id):
    """Test REST API POST, GET and DELETE reqs.

    Tries to create new object, gets accession id and checks if correct
    resource is returned with that id. Finally deletes the object and checks it
    was deleted.

    :param sess: HTTP session in which request call is made
    :param schema: name of the schema (submission) used for testing
    :param filename: name of the file used for testing
    :param submission_id: id of the submission used to group submission
    """
    accession_id = await post_object(sess, schema, submission_id, filename)
    async with sess.get(f"{objects_url}/{schema}/{accession_id[0]}") as resp:
        LOG.debug(f"Checking that {accession_id[0]} JSON is in {schema}")
        assert resp.status == 200, f"HTTP Status code error, got {resp.status}"
        res = await resp.json()
        title = res["descriptor"].get("studyTitle", "") if schema == "study" else res.get("title", "")
    await check_submissions_object_patch(sess, submission_id, schema, accession_id[0], title, filename)
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

    async with sess.get(f"{submissions_url}/{submission_id}") as resp:
        LOG.debug(f"Checking that object {accession_id[0]} was deleted from submission {submission_id}")
        res = await resp.json()
        expected_true = not any(d["accessionId"] == accession_id[0] for d in res["metadataObjects"])
        assert expected_true, f"object {accession_id[0]} still exists"


async def test_crud_with_multi_xml(sess, submission_id):
    """Test CRUD for a submitted XML file with multiple metadata objects.

    Tries to create new objects, gets accession ids and checks if correct
    resource is returned with those ids. Finally deletes the objects and checks it
    was deleted.

    :param sess: HTTP session in which request call is made
    :param submission_id: id of the submission used to group submission
    """
    items = []
    _schema = "policy"
    _filename = "policy2.xml"
    data = await post_multi_object(sess, _schema, submission_id, _filename)
    for item in data:
        items.append(item)
        async with sess.get(f"{objects_url}/{_schema}/{item['accessionId']}") as resp:
            LOG.debug(f"Checking that {item['accessionId']} JSON is in {_schema}")
            assert resp.status == 200, f"HTTP Status code error, got {resp.status}"
        async with sess.get(f"{objects_url}/{_schema}/{item['accessionId']}?format=xml") as resp:
            LOG.debug(f"Checking that {item['accessionId']} XML is in {_schema}")
            assert resp.status == 200, f"HTTP Status code error, got {resp.status}"

    _schema = "image"
    _filename = "images_multi.xml"
    data = await post_multi_object(sess, _schema, submission_id, _filename)
    for item in data:
        items.append(item)
        async with sess.get(f"{objects_url}/{_schema}/{item['accessionId']}") as resp:
            LOG.debug(f"Checking that {item['accessionId']} JSON is in {_schema}")
            assert resp.status == 200, f"HTTP Status code error, got {resp.status}"
        async with sess.get(f"{objects_url}/{_schema}/{item['accessionId']}?format=xml") as resp:
            LOG.debug(f"Checking that {item['accessionId']} XML is in {_schema}")
            assert resp.status == 200, f"HTTP Status code error, got {resp.status}"

    _schema = "bpsample"
    _filename = "template_samples.xml"
    data = await post_multi_object(sess, _schema, submission_id, _filename)
    for item in data:
        items.append(item)
        async with sess.get(f"{objects_url}/{_schema}/{item['accessionId']}") as resp:
            LOG.debug(f"Checking that {item['accessionId']} JSON is in {_schema}")
            assert resp.status == 200, f"HTTP Status code error, got {resp.status}"
            res = await resp.json()
            LOG.debug(res)
        async with sess.get(f"{objects_url}/{_schema}/{item['accessionId']}?format=xml") as resp:
            LOG.debug(f"Checking that {item['accessionId']} XML is in {_schema}")
            assert resp.status == 200, f"HTTP Status code error, got {resp.status}"

    assert len(items) == 14, "Wrong amount of items were added during previous requests."
    for item in items:
        _id, _schema = item["accessionId"], item["schema"]
        await delete_object(sess, _schema, _id)
        async with sess.get(f"{objects_url}/{_schema}/{_id}") as resp:
            LOG.debug(f"Checking that JSON object {_id} was deleted")
            assert resp.status == 404, f"HTTP Status code error, got {resp.status}"
        async with sess.get(f"{objects_url}/{_schema}/{_id}?format=xml") as resp:
            LOG.debug(f"Checking that XML object {_id} was deleted")
            assert resp.status == 404, f"HTTP Status code error, got {resp.status}"


async def test_csv(sess, submission_id):
    """Test CRUD for a submitted CSV file.

    Test tries with good csv file first for sample object, after which we try with empty file.
    After this we try with study object which is not allowed.

    :param sess: HTTP session in which request call is made
    :param submission_id: id of the submission used to group submission
    """
    _schema = "sample"
    _filename = "EGAformat.csv"
    samples = await post_object(sess, _schema, submission_id, _filename)
    # there are 3 rows and we expected to get 3rd
    assert len(samples[0]) == 3, f"expected nb of CSV entries does not match, we got: {len(samples[0])}"
    # _first_csv_row_id = accession_id[0][0]["accessionId"]
    first_sample = samples[0][0]["accessionId"]

    async with sess.get(f"{objects_url}/{_schema}/{first_sample}") as resp:
        LOG.debug(f"Checking that {first_sample} JSON is in {_schema}")
        assert resp.status == 200, f"HTTP Status code error, got {resp.status}"
        res = await resp.json()
        title = res.get("title", "")
    await check_submissions_object_patch(sess, submission_id, _schema, samples, title, _filename)

    await delete_object(sess, _schema, first_sample)
    async with sess.get(f"{objects_url}/{_schema}/{first_sample}") as resp:
        LOG.debug(f"Checking that JSON object {first_sample} was deleted")
        assert resp.status == 404, f"HTTP Status code error, got {resp.status}"

    async with sess.get(f"{submissions_url}/{submission_id}") as resp:
        LOG.debug(f"Checking that object {first_sample} was deleted from submission {submission_id}")
        res = await resp.json()
        expected_true = not any(d["accessionId"] == first_sample for d in res["metadataObjects"])
        assert expected_true, f"object {first_sample} still exists"

    _filename = "empty.csv"
    # status should be 400
    await post_object_expect_status(sess, _schema, submission_id, _filename, 400)

    _filename = "EGA_sample_w_issue.csv"
    # status should be 201 but we expect 3 rows, as the CSV has 4 rows one of which is empty
    samples_2 = await post_object_expect_status(sess, _schema, submission_id, _filename, 201)
    assert len(samples_2[0]) == 3, f"expected nb of CSV entries does not match, we got: {len(samples_2[0])}"

    for sample in samples_2[0] + samples[0][1:]:
        await delete_object(sess, _schema, sample["accessionId"])


async def test_put_objects(sess, submission_id):
    """Test PUT reqs.

    Tries to create new object, gets accession id and checks if correct
    resource is returned with that id. Try to use PUT with JSON and expect failure,
    try to use PUT with XML and expect success.

    :param sess: HTTP session in which request call is made
    :param submission_id: id of the submission used to group submission
    """
    accession_id = await post_object(sess, "study", submission_id, "SRP000539.xml")
    await put_object_json(sess, "study", accession_id[0], "SRP000539.json")
    await put_object_xml(sess, "study", accession_id[0], "SRP000539_put.xml")
    await check_submissions_object_patch(
        sess,
        submission_id,
        "study",
        accession_id,
        "Highly integrated epigenome maps in Arabidopsis - whole genome shotgun bisulfite sequencing",
        "SRP000539_put.xml",
    )
    await delete_object(sess, "study", accession_id[0])


async def test_crud_drafts_works(sess, schema, orginal_file, update_file, submission_id):
    """Test drafts REST API POST, PUT and DELETE reqs.

    Tries to create new draft object, gets accession id and checks if correct
    resource is returned with that id. Finally deletes the object and checks it
    was deleted.

    :param sess: HTTP session in which request call is made
    :param schema: name of the schema (submission) used for testing
    :param orginal_file: name of the file used for creating object.
    :param update_file: name of the file used for updating object.
    :param submission_id: id of the submission used to group submission objects
    """
    draft_id = await post_draft_json(sess, schema, submission_id, orginal_file)
    async with sess.get(f"{drafts_url}/{schema}/{draft_id}") as resp:
        assert resp.status == 200, f"HTTP Status code error, got {resp.status}"
        res = await resp.json()
        title = res["descriptor"]["studyTitle"] if schema == "study" else res.get("title", "")
    await check_submissions_object_patch(sess, submission_id, draft_id, schema, title, orginal_file, draft=True)

    accession_id = await put_draft(sess, schema, draft_id, update_file)
    async with sess.get(f"{drafts_url}/{schema}/{accession_id}") as resp:
        LOG.debug(f"Checking that {accession_id} JSON is in {schema}")
        assert resp.status == 200, f"HTTP Status code error, got {resp.status}"
        res = await resp.json()
        title = res["descriptor"]["studyTitle"] if schema == "study" else res.get("title", "")
    await check_submissions_object_patch(sess, submission_id, schema, accession_id, title, update_file, draft=True)

    await delete_draft(sess, schema, accession_id)
    async with sess.get(f"{drafts_url}/{schema}/{accession_id}") as resp:
        LOG.debug(f"Checking that JSON object {accession_id} was deleted")
        assert resp.status == 404, f"HTTP Status code error, got {resp.status}"

    async with sess.get(f"{submissions_url}/{submission_id}") as resp:
        LOG.debug(f"Checking that JSON object {accession_id} was deleted from submission {submission_id}")
        res = await resp.json()
        expected_true = not any(d["accessionId"] == accession_id for d in res["drafts"])
        assert expected_true, f"draft object {accession_id} still exists"


async def test_patch_drafts_works(sess, schema, orginal_file, update_file, submission_id):
    """Test REST API POST, PATCH and DELETE reqs.

    Tries to create put and patch object, gets accession id and
    checks if correct resource is returned with that id.
    Finally deletes the object and checks it was deleted.

    :param sess: HTTP session in which request call is made
    :param schema: name of the schema (submission) used for testing
    :param orginal_file: name of the file used for creating object.
    :param update_file: name of the file used for updating object.
    :param submission_id: id of the submission used to group submission objects
    """
    draft_id = await post_draft_json(sess, schema, submission_id, orginal_file)
    accession_id = await patch_draft(sess, schema, draft_id, update_file)
    async with sess.get(f"{drafts_url}/{schema}/{accession_id}") as resp:
        LOG.debug(f"Checking that {accession_id} JSON is in {schema}")
        res = await resp.json()
        title = res["descriptor"]["studyTitle"] if schema == "study" else res.get("title", None)
        assert res["centerName"] == "GEOM", "object centerName content mismatch"
        assert res["alias"] == "GSE10968", "object alias content mismatch"
        assert resp.status == 200, f"HTTP Status code error, got {resp.status}"
    await check_submissions_object_patch(sess, submission_id, schema, accession_id, title, update_file, draft=True)

    await delete_draft(sess, schema, accession_id)
    async with sess.get(f"{drafts_url}/{schema}/{accession_id}") as resp:
        LOG.debug(f"Checking that JSON object {accession_id} was deleted")
        assert resp.status == 404, f"HTTP Status code error, got {resp.status}"


async def test_querying_works(sess, submission_id):
    """Test query endpoint with working and failing query.

    :param sess: HTTP session in which request call is made
    :param submission_id: id of the submission used to group submission objects
    """
    files = await asyncio.gather(
        *[post_object(sess, schema, submission_id, filename) for schema, filename in test_xml_files]
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
        LOG.debug(f"Querying {schema} collection with non-working params")
        invalid = "yoloswaggings"
        await asyncio.gather(*[do_one_query(schema, key, invalid, 404) for key, _ in schema_queries])

    await asyncio.gather(*[delete_object(sess, schema, accession_id) for accession_id, schema in files])


async def test_getting_all_objects_from_schema_works(sess, submission_id):
    """Check that /objects/study returns objects with correct pagination.

    :param sess: HTTP session in which request call is made
    :param submission_id: id of the submission used to group submission objects
    """
    # Add objects
    files = await asyncio.gather(*[post_object(sess, "sample", submission_id, "SRS001433.xml") for _ in range(13)])

    # Test default values
    async with sess.get(f"{objects_url}/sample") as resp:
        assert resp.status == 200
        ans = await resp.json()
        assert ans["page"]["page"] == 1
        assert ans["page"]["size"] == 10
        assert ans["page"]["totalPages"] == 2
        assert ans["page"]["totalObjects"] == 13, ans["page"]["totalObjects"]
        assert len(ans["objects"]) == 10

    # Test with custom pagination values
    async with sess.get(f"{objects_url}/sample?page=2&per_page=3") as resp:
        assert resp.status == 200
        ans = await resp.json()
        assert ans["page"]["page"] == 2
        assert ans["page"]["size"] == 3
        assert ans["page"]["totalPages"] == 5, ans["page"]["totalPages"]
        assert ans["page"]["totalObjects"] == 13, ans["page"]["totalObjects"]
        assert len(ans["objects"]) == 3

    # Test with wrong pagination values
    async with sess.get(f"{objects_url}/sample?page=-1") as resp:
        assert resp.status == 400
    async with sess.get(f"{objects_url}/sample?per_page=0") as resp:
        assert resp.status == 400

    # Delete objects
    await asyncio.gather(*[delete_object(sess, "sample", accession_id) for accession_id, _ in files])


async def test_metax_crud_with_xml(sess, submission_id):
    """Test Metax service with study and dataset xml files POST, PATCH, PUBLISH and DELETE reqs.

    :param sess: HTTP session in which request call is made
    :param submission_id: id of the submission where objects reside
    """
    # POST to object endpoint creates draft dataset in Metax for Study and Dataset
    ids = []
    xml_files = set()
    for schema, filename, update_filename in {
        ("study", "SRP000539.xml", "SRP000539_put.xml"),
        ("dataset", "dataset.xml", "dataset_put.xml"),
    }:
        accession_id, _ = await post_object(sess, schema, submission_id, filename)
        xml_files.add((schema, accession_id, update_filename))
        ids.append([schema, accession_id])

    for object in ids:
        schema, accession_id = object
        async with sess.get(f"{objects_url}/{schema}/{accession_id}") as resp:
            assert resp.status == 200, f"HTTP Status code error, got {resp.status}"
            res = await resp.json()
            try:
                metax_id = res["metaxIdentifier"]
            except KeyError:
                assert False, "Metax ID was not in response data"
        object.append(metax_id)
        async with sess.get(f"{metax_url}/{metax_id}", auth=auth) as metax_resp:
            assert metax_resp.status == 200, f"HTTP Status code error, got {metax_resp.status}"
            metax_res = await metax_resp.json()
            assert (
                res.get("doi", None) == metax_res["research_dataset"]["preferred_identifier"]
            ), "Object's DOI was not in Metax response data preferred_identifier"

    # PUT and PATCH to object endpoint updates draft dataset in Metax for Study and Dataset
    for schema, accession_id, filename in xml_files:
        await put_object_xml(sess, schema, accession_id, filename)

    for _, _, metax_id in ids:
        async with sess.get(f"{metax_url}/{metax_id}", auth=auth) as metax_resp:
            assert metax_resp.status == 200, f"HTTP Status code error, got {metax_resp.status}"
            metax_res = await metax_resp.json()
            assert (
                metax_res.get("date_modified", None) is not None
            ), f"Object with metax id {metax_res['identifier']} was not updated in Metax"

    # DELETE object from Metax
    for schema, accession_id, _ in xml_files:
        await delete_object(sess, schema, accession_id)

    for _, _, metax_id in ids:
        async with sess.get(f"{metax_url}/{metax_id}", auth=auth) as metax_resp:
            assert metax_resp.status == 404, f"HTTP Status code error - expected 404 Not Found, got {metax_resp.status}"


async def test_metax_crud_with_json(sess, submission_id):
    """Test Metax service with study and dataset json data POST, PATCH, PUBLISH and DELETE reqs.

    :param sess: HTTP session in which request call is made
    :param submission_id: id of the submission where objects reside
    """
    ids = []
    json_files = set()
    for schema, filename, update_filename in {
        ("study", "SRP000539.json", "patch.json"),
        ("dataset", "dataset.json", "dataset_patch.json"),
    }:
        accession_id = await post_object_json(sess, schema, submission_id, filename)
        json_files.add((schema, accession_id, filename, update_filename))
        ids.append([schema, accession_id])

    for object in ids:
        schema, accession_id = object
        async with sess.get(f"{objects_url}/{schema}/{accession_id}") as resp:
            assert resp.status == 200, f"HTTP Status code error, got {resp.status}"
            res = await resp.json()
            try:
                metax_id = res["metaxIdentifier"]
            except KeyError:
                assert False, "Metax ID was not in response data"
        object.append(metax_id)
        async with sess.get(f"{metax_url}/{metax_id}", auth=auth) as metax_resp:
            assert metax_resp.status == 200, f"HTTP Status code error, got {metax_resp.status}"
            metax_res = await metax_resp.json()
            assert (
                res.get("doi", None) == metax_res["research_dataset"]["preferred_identifier"]
            ), "Object's DOI was not in Metax response data preferred_identifier"

    for schema, accession_id, filename, _ in json_files:
        await put_object_json(sess, schema, accession_id, filename)
    for schema, accession_id, _, filename in json_files:
        await patch_object_json(sess, schema, accession_id, filename)

    for schema, accession_id, _, _ in json_files:
        await delete_object(sess, schema, accession_id)


async def test_metax_id_not_updated_on_patch(sess, submission_id):
    """Test that Metax id cannot be sent in patch.

    :param sess: HTTP session in which request call is made
    :param submission_id: id of the submission where objects reside
    """
    for schema, filename in {
        ("study", "SRP000539.json"),
        ("dataset", "dataset.json"),
    }:
        accession_id = await post_object_json(sess, schema, submission_id, filename)
        async with sess.patch(f"{objects_url}/{schema}/{accession_id}", data={"metaxIdentifier": "12345"}) as resp:
            LOG.debug(f"Trying to patch object in {schema}")
            assert resp.status == 400

            await delete_object(sess, schema, accession_id)


async def test_metax_publish_dataset(sess, submission_id):
    """Test publishing dataset to Metax service after submission(submission) is published.

    :param sess: HTTP session in which request call is made
    :param submission_id: id of the submission where objects reside
    """
    # POST to object endpoint creates draft dataset in Metax for Study and Dataset
    objects = []
    for schema, filename in {
        ("study", "SRP000539.xml"),
        ("dataset", "dataset.xml"),
    }:
        accession_id, _ = await post_object(sess, schema, submission_id, filename)
        objects.append([schema, accession_id])

    for object in objects:
        schema, object_id = object
        async with sess.get(f"{objects_url}/{schema}/{object_id}") as resp:
            assert resp.status == 200, f"HTTP Status code error, got {resp.status}"
            res = await resp.json()
            object.append(res["metaxIdentifier"])

    # Add DOI and publish the submission
    doi_data_raw = await create_request_json_data("doi", "test_doi.json")
    await put_submission_doi(sess, submission_id, doi_data_raw)
    dac_data = await create_request_json_data("dac", "dac_rems.json")
    await put_submission_dac(sess, submission_id, dac_data)
    await publish_submission(sess, submission_id)

    for schema, object_id, metax_id in objects:
        async with sess.get(f"{objects_url}/{schema}/{object_id}") as resp:
            assert resp.status == 200, f"HTTP Status code error, got {resp.status}"
            res = await resp.json()
            assert res["metaxIdentifier"] == metax_id

        async with sess.get(f"{metax_url}/{metax_id}") as metax_resp:
            assert metax_resp.status == 200, f"HTTP Status code error, got {metax_resp.status}"
            metax_res = await metax_resp.json()
            assert metax_res["state"] == "published", f"{schema}  {metax_res}"

            # this data is synced with /test_files/doi/test_doi.json
            # if data changes inside the file it must data must be reflected here
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

            if schema == "study":
                assert "relation" in actual_rd
                study_dataset_relation = actual_rd["relation"][0]["entity"]["identifier"].split("/")[-1]
                study_metax_id = metax_id
            if schema == "dataset":
                assert "is_output_of" in actual_rd
                dataset_output_study = actual_rd["is_output_of"][0]["identifier"].split("/")[-1]
                dataset_metax_id = metax_id

    assert study_dataset_relation == dataset_metax_id
    assert dataset_output_study == study_metax_id

    for _, _, metax_id in objects:
        # delete of published metax datasets is possible only from mocked metax for testing purpose
        # Metax service does not allow deleting published datasets
        await sess.delete(f"{metax_url}/{metax_id}", params={"test": "true"})


async def test_metax_publish_dataset_with_missing_metax_id(sess, database, submission_id):
    """Test publishing dataset to Metax service after submission(submission) is failed to create Metax draft dataset.

    Test will create study and dataset normally. After that imitating missing Metax connection will be done
    with deleting object's metax ID and making call to mocked Metax service to remove Metax dataset from drafts.
    Then objects will be published in metadata-submitter which should start a flow of creating draft dataset to Metax
    and only then publishing it.

    :param sess: HTTP session in which request call is made
    :param submission_id: id of the submission where objects reside
    """
    objects = []
    for schema, filename in {
        ("study", "SRP000539.xml"),
        ("dataset", "dataset.xml"),
    }:
        accession_id, _ = await post_object(sess, schema, submission_id, filename)
        async with sess.get(f"{objects_url}/{schema}/{accession_id}") as resp:
            res = await resp.json()
            metax_id = res["metaxIdentifier"]
        objects.append([schema, accession_id])
        await delete_objects_metax_id(sess, database, schema, accession_id, metax_id)
        async with sess.get(f"{objects_url}/{schema}/{accession_id}") as resp:
            res = await resp.json()
            assert res["metaxIdentifier"] == ""

    # Add DOI and publish the submission
    doi_data_raw = await create_request_json_data("doi", "test_doi.json")
    await put_submission_doi(sess, submission_id, doi_data_raw)
    dac_data = await create_request_json_data("dac", "dac_rems.json")
    await put_submission_dac(sess, submission_id, dac_data)
    await publish_submission(sess, submission_id)

    for schema, accession_id in objects:
        async with sess.get(f"{objects_url}/{schema}/{accession_id}") as resp:
            assert resp.status == 200, f"HTTP Status code error, got {resp.status}"
            res = await resp.json()
            assert res["metaxIdentifier"] != ""


async def test_crud_submissions_works(sess, project_id):
    """Test submissions REST api POST, GET, PATCH, PUBLISH and DELETE reqs.

    :param sess: HTTP session in which request call is made
    :param project_id: id of the project the submission belongs to
    """
    # Create new submission and check its creation succeeded
    submission_data = {
        "name": "Mock Submission",
        "description": "Mock Base submission to submission ops",
        "projectId": project_id,
    }
    submission_id = await post_submission(sess, submission_data)
    async with sess.get(f"{submissions_url}/{submission_id}") as resp:
        LOG.debug(f"Checking that submission {submission_id} was created")
        assert resp.status == 200, f"HTTP Status code error, got {resp.status}"

    # Create draft from test XML file and patch the draft into the newly created submission
    draft_id = await post_draft(sess, "sample", submission_id, "SRS001433.xml")
    async with sess.get(f"{submissions_url}/{submission_id}") as resp:
        LOG.debug(f"Checking that submission {submission_id} was patched")
        res = await resp.json()
        assert res["submissionId"] == submission_id, "expected submission id does not match"
        assert res["name"] == submission_data["name"], "expected submission name does not match"
        assert res["description"] == submission_data["description"], "submission description content mismatch"
        assert res["published"] is False, "submission is published, expected False"
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
        ], f'submission drafts content mismatch, {res["drafts"]}'
        assert res["metadataObjects"] == [], "there are objects in submission, expected empty"

    # Get the draft from the collection within this session and post it to objects collection
    draft_data = await get_draft(sess, "sample", draft_id)
    async with sess.post(f"{objects_url}/sample", params={"submission": submission_id}, data=draft_data) as resp:
        LOG.debug("Adding draft to actual objects")
        assert resp.status == 201, f"HTTP Status code error, got {resp.status}"
        ans = await resp.json()
        assert ans["accessionId"] != draft_id, "draft id does not match expected"
        accession_id = ans["accessionId"]

    async with sess.get(f"{submissions_url}/{submission_id}") as resp:
        LOG.debug(f"Checking that submission {submission_id} was patched")
        res = await resp.json()
        assert res["submissionId"] == submission_id, "expected submission id does not match"
        assert res["published"] is False, "submission is published, expected False"
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
        ], f'submission drafts content mismatch, {res["drafts"]}'
        assert res["metadataObjects"] == [
            {
                "accessionId": accession_id,
                "schema": "sample",
                "tags": {"submissionType": "Form", "displayTitle": "HapMap sample from Homo sapiens"},
            }
        ], "submission metadataObjects content mismatch"

    # Add DOI for publishing the submission
    doi_data_raw = await create_request_json_data("doi", "test_doi.json")
    await put_submission_doi(sess, submission_id, doi_data_raw)

    # add a study and dataset for publishing a submission
    ds_1 = await post_object(sess, "dataset", submission_id, "dataset.xml")
    ds_1 = await get_object(sess, "dataset", ds_1[0])

    study = await post_object_json(sess, "study", submission_id, "SRP000539.json")
    study = await get_object(sess, "study", study)

    ds_2 = await post_object(sess, "dataset", submission_id, "dataset_put.xml")
    ds_2 = await get_object(sess, "dataset", ds_2[0])

    dac_data = await create_request_json_data("dac", "dac_rems.json")
    await put_submission_dac(sess, submission_id, dac_data)

    submission_id = await publish_submission(sess, submission_id)

    await get_draft(sess, "sample", draft_id, 404)  # checking the draft was deleted after publication

    async with sess.get(f"{submissions_url}/{submission_id}") as resp:
        LOG.debug(f"Checking that submission {submission_id} was patched")
        res = await resp.json()
        assert res["submissionId"] == submission_id, "expected submission id does not match"
        assert res["published"] is True, "submission is not published, expected True"
        assert "datePublished" in res.keys()
        assert "extraInfo" in res.keys()
        assert res["drafts"] == [], "there are drafts in submission, expected empty"
        assert len(res["metadataObjects"]) == 4, "submission metadataObjects content mismatch"

    # check that datacite has references between datasets and study
    async with sess.get(f"{datacite_url}/{ds_1['doi']}") as datacite_resp:
        assert datacite_resp.status == 200, f"HTTP Status code error, got {datacite_resp.status}"
        datacite_res = await datacite_resp.json()
        ds_1 = datacite_res["data"]
    async with sess.get(f"{datacite_url}/{ds_2['doi']}") as datacite_resp:
        assert datacite_resp.status == 200, f"HTTP Status code error, got {datacite_resp.status}"
        datacite_res = await datacite_resp.json()
        ds_2 = datacite_res["data"]
    async with sess.get(f"{datacite_url}/{study['doi']}") as datacite_resp:
        assert datacite_resp.status == 200, f"HTTP Status code error, got {datacite_resp.status}"
        datacite_res = await datacite_resp.json()
        study = datacite_res["data"]
    assert ds_1["data"]["attributes"]["relatedIdentifiers"][0]["relatedIdentifier"] == study["id"]
    assert ds_2["data"]["attributes"]["relatedIdentifiers"][0]["relatedIdentifier"] == study["id"]
    for id in study["data"]["attributes"]["relatedIdentifiers"]:
        assert id["relatedIdentifier"] in {ds_1["id"], ds_2["id"]}

    # Delete submission
    await delete_submission_publish(sess, submission_id)

    async with sess.get(f"{drafts_url}/sample/{draft_id}") as resp:
        LOG.debug(f"Checking that JSON object {accession_id} was deleted")
        assert resp.status == 404, f"HTTP Status code error, got {resp.status}"


async def test_bpdataset_gets_doi(sess, project_id):
    """Test bp dataset has doi generated.

    :param sess: HTTP session in which request call is made
    :param project_id: id of the project the submission belongs to
    """
    # Create new submission
    submission_data = {
        "name": "Test bpdataset submission",
        "description": "Test that DOI is generated for bp dataset",
        "projectId": project_id,
    }
    submission_id = await post_submission(sess, submission_data)

    # Submit study, bpdataset
    study = await post_object_json(sess, "study", submission_id, "SRP000539.json")
    study = await get_object(sess, "study", study)

    bpdataset = post_object(sess, "bpdataset", submission_id, "template_dataset.xml")
    bpdataset = await get_object(sess, "bpdataset", bpdataset[0])
    assert bpdataset["doi"] is not None

    # Add DOI for publishing the submission
    doi_data_raw = await create_request_json_data("doi", "test_doi.json")
    await put_submission_doi(sess, submission_id, doi_data_raw)

    submission_id = await publish_submission(sess, submission_id)

    # check that datacite has references between datasets and study
    async with sess.get(f"{datacite_url}/{bpdataset['doi']}") as datacite_resp:
        assert datacite_resp.status == 200, f"HTTP Status code error, got {datacite_resp.status}"
        datacite_res = await datacite_resp.json()
        bpdataset = datacite_res["data"]

    async with sess.get(f"{datacite_url}/{study['doi']}") as datacite_resp:
        assert datacite_resp.status == 200, f"HTTP Status code error, got {datacite_resp.status}"
        datacite_res = await datacite_resp.json()
        study = datacite_res["data"]
    assert bpdataset["data"]["attributes"]["relatedIdentifiers"][0]["relatedIdentifier"] == study["id"]
    for id in study["data"]["attributes"]["relatedIdentifiers"]:
        assert study["data"]["attributes"]["relatedIdentifiers"][0]["relatedIdentifier"] == bpdataset["id"]

    # Delete submission
    await delete_submission_publish(sess, submission_id)


async def test_crud_submissions_works_no_publish(sess, project_id):
    """Test submissions REST API POST, GET, PATCH, PUBLISH and DELETE reqs.

    :param sess: HTTP session in which request call is made
    :param project_id: id of the project the submission belongs to
    """
    # Create new submission and check its creation succeeded
    submission_data = {
        "name": "Mock Unpublished submission",
        "description": "test umpublished submission",
        "projectId": project_id,
    }
    submission_id = await post_submission(sess, submission_data)
    async with sess.get(f"{submissions_url}/{submission_id}") as resp:
        LOG.debug(f"Checking that submission {submission_id} was created")
        assert resp.status == 200, f"HTTP Status code error, got {resp.status}"

    # Create draft from test XML file and patch the draft into the newly created submission
    draft_id = await post_draft(sess, "sample", submission_id, "SRS001433.xml")
    async with sess.get(f"{submissions_url}/{submission_id}") as resp:
        LOG.debug(f"Checking that submission {submission_id} was patched")
        res = await resp.json()
        assert res["submissionId"] == submission_id, "expected submission id does not match"
        assert res["name"] == submission_data["name"], "expected submission name does not match"
        assert res["description"] == submission_data["description"], "submission description content mismatch"
        assert res["published"] is False, "submission is published, expected False"
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
        ], "submission drafts content mismatch"
        assert res["metadataObjects"] == [], "there are objects in submission, expected empty"

    # Get the draft from the collection within this session and post it to objects collection
    draft = await get_draft(sess, "sample", draft_id)
    async with sess.post(f"{objects_url}/sample", params={"submission": submission_id}, data=draft) as resp:
        LOG.debug("Adding draft to actual objects")
        assert resp.status == 201, f"HTTP Status code error, got {resp.status}"
        ans = await resp.json()
        assert ans["accessionId"] != draft_id, "draft id does not match expected"
        accession_id = ans["accessionId"]

    async with sess.get(f"{submissions_url}/{submission_id}") as resp:
        LOG.debug(f"Checking that submission {submission_id} was patched")
        res = await resp.json()
        assert res["submissionId"] == submission_id, "expected submission id does not match"
        assert res["published"] is False, "submission is published, expected False"
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
        ], "submission drafts content mismatch"
        assert res["metadataObjects"] == [
            {
                "accessionId": accession_id,
                "schema": "sample",
                "tags": {"submissionType": "Form", "displayTitle": "HapMap sample from Homo sapiens"},
            }
        ], "submission metadataObjects content mismatch"

    # Delete submission
    await delete_submission(sess, submission_id)
    async with sess.get(f"{submissions_url}/{submission_id}") as resp:
        LOG.debug(f"Checking that submission {submission_id} was deleted")
        assert resp.status == 404, f"HTTP Status code error, got {resp.status}"


async def test_adding_doi_info_to_submission_works(sess, project_id):
    """Test that proper DOI info can be added to submission and bad DOI info cannot be.

    :param sess: HTTP session in which request call is made
    :param project_id: id of the project the submission belongs to
    """
    # Create new submission and check its creation succeeded
    submission_data = {
        "name": "DOI Submission",
        "description": "Mock Base submission for adding DOI info",
        "projectId": project_id,
    }
    submission_id = await post_submission(sess, submission_data)
    async with sess.get(f"{submissions_url}/{submission_id}") as resp:
        LOG.debug(f"Checking that submission {submission_id} was created")
        assert resp.status == 200, f"HTTP Status code error, got {resp.status}"

    # Get correctly formatted DOI info and patch it into the new submission successfully
    doi_data_raw = await create_request_json_data("doi", "test_doi.json")
    doi_data = json.loads(doi_data_raw)
    await put_submission_doi(sess, submission_id, doi_data_raw)

    async with sess.get(f"{submissions_url}/{submission_id}") as resp:
        LOG.debug(f"Checking that submission {submission_id} was patched")
        res = await resp.json()
        assert res["submissionId"] == submission_id, "expected submission id does not match"
        assert res["name"] == submission_data["name"], "expected submission name does not match"
        assert res["description"] == submission_data["description"], "submission description content mismatch"
        assert res["published"] is False, "submission is published, expected False"
        assert res["doiInfo"] == doi_data, "submission doi does not match"

    # Test that an incomplete DOI object fails to patch into the submission
    put_bad_doi = {"identifier": {}}
    async with sess.put(f"{submissions_url}/{submission_id}/doi", data=json.dumps(put_bad_doi)) as resp:
        LOG.debug(f"Tried updating submission {submission_id}")
        assert resp.status == 400, f"HTTP Status code error, got {resp.status}"
        res = await resp.json()
        assert res["detail"] == "Provided input does not seem correct for field: 'doiInfo'", "expected error mismatch"

    # Check the existing DOI info is not altered
    async with sess.get(f"{submissions_url}/{submission_id}") as resp:
        LOG.debug(f"Checking that submission {submission_id} was not patched with bad DOI")
        res = await resp.json()
        assert res["doiInfo"] == doi_data, "submission doi does not match"

    # Test that extraInfo cannot be altered
    patch_add_bad_doi = [{"op": "add", "path": "/extraInfo", "value": {"publisher": "something"}}]
    async with sess.patch(f"{submissions_url}/{submission_id}", data=json.dumps(patch_add_bad_doi)) as resp:
        LOG.debug(f"Tried updating submission {submission_id}")
        assert resp.status == 400, f"HTTP Status code error, got {resp.status}"
        res = await resp.json()
        detail = res["detail"]
        assert (
            detail == "Patch submission operation should be provided as a JSON object"
        ), f"error mismatch, got '{detail}'"

    # Delete submission
    await delete_submission(sess, submission_id)
    async with sess.get(f"{submissions_url}/{submission_id}") as resp:
        LOG.debug(f"Checking that submission {submission_id} was deleted")
        assert resp.status == 404, f"HTTP Status code error, got {resp.status}"


async def test_getting_paginated_submissions(sess, project_id):
    """Check that /submissions returns submissions with correct pagination.

    :param sess: HTTP session in which request call is made
    :param project_id: id of the project the submission belongs to
    """
    # Test default values
    async with sess.get(f"{submissions_url}?projectId={project_id}") as resp:
        # The submissions received here are from previous
        # tests where the submissions were not deleted
        assert resp.status == 200
        ans = await resp.json()
        assert ans["page"]["page"] == 1
        assert ans["page"]["size"] == 5
        assert ans["page"]["totalPages"] == 2
        assert ans["page"]["totalSubmissions"] == 9
        assert len(ans["submissions"]) == 5

    # Test with custom pagination values
    async with sess.get(f"{submissions_url}?page=2&per_page=3&projectId={project_id}") as resp:
        assert resp.status == 200
        ans = await resp.json()
        assert ans["page"]["page"] == 2
        assert ans["page"]["size"] == 3
        assert ans["page"]["totalPages"] == 3
        assert ans["page"]["totalSubmissions"] == 9
        assert len(ans["submissions"]) == 3

    # Test querying only published submissions
    async with sess.get(f"{submissions_url}?published=true&projectId={project_id}") as resp:
        assert resp.status == 200
        ans = await resp.json()
        assert ans["page"]["page"] == 1
        assert ans["page"]["size"] == 5
        assert ans["page"]["totalPages"] == 1
        assert ans["page"]["totalSubmissions"] == 3
        assert len(ans["submissions"]) == 3

    # Test querying only draft submissions
    async with sess.get(f"{submissions_url}?published=false&projectId={project_id}") as resp:
        assert resp.status == 200
        ans = await resp.json()
        assert ans["page"]["page"] == 1
        assert ans["page"]["size"] == 5
        assert ans["page"]["totalPages"] == 2
        assert ans["page"]["totalSubmissions"] == 6
        assert len(ans["submissions"]) == 5

    # Test with wrong pagination values
    async with sess.get(f"{submissions_url}?page=-1&projectId={project_id}") as resp:
        assert resp.status == 400
    async with sess.get(f"{submissions_url}?per_page=0&projectId={project_id}") as resp:
        assert resp.status == 400
    async with sess.get(f"{submissions_url}?published=asdf&projectId={project_id}") as resp:
        assert resp.status == 400


async def test_getting_submissions_filtered_by_name(sess, project_id):
    """Check that /submissions returns submissions filtered by name.

    :param sess: HTTP session in which request call is made
    :param project_id: id of the project the submission belongs to
    """
    names = [" filter new ", "_filter_", "-filter-", "_extra-", "_2021special_"]
    submissions = []
    for name in names:
        submission_data = {"name": f"Test{name}name", "description": "Test filtering name", "projectId": project_id}
        submissions.append(await post_submission(sess, submission_data))

    async with sess.get(f"{submissions_url}?name=filter&projectId={project_id}") as resp:
        ans = await resp.json()
        assert resp.status == 200, f"HTTP Status code error {resp.status} {ans}"
        assert ans["page"]["totalSubmissions"] == 3, f'Shold be 3 returned {ans["page"]["totalSubmissions"]}'

    async with sess.get(f"{submissions_url}?name=extra&projectId={project_id}") as resp:
        ans = await resp.json()
        assert resp.status == 200, f"HTTP Status code error {resp.status} {ans}"
        assert ans["page"]["totalSubmissions"] == 1

    async with sess.get(f"{submissions_url}?name=2021 special&projectId={project_id}") as resp:
        assert resp.status == 200
        ans = await resp.json()
        assert ans["page"]["totalSubmissions"] == 0

    async with sess.get(f"{submissions_url}?name=new extra&projectId={project_id}") as resp:
        assert resp.status == 200
        ans = await resp.json()
        assert ans["page"]["totalSubmissions"] == 2

    for submission in submissions:
        await delete_submission(sess, submission)


async def test_getting_submissions_filtered_by_date_created(sess, database, project_id):
    """Check that /submissions returns submissions filtered by date created.

    :param sess: HTTP session in which request call is made
    :param database: database client to perform db operations
    :param project_id: id of the project the submission belongs to
    """
    submissions = []
    format = "%Y-%m-%d %H:%M:%S"

    # Test dateCreated within a year
    # Create submissions with different dateCreated
    timestamps = ["2014-12-31 00:00:00", "2015-01-01 00:00:00", "2015-07-15 00:00:00", "2016-01-01 00:00:00"]
    for stamp in timestamps:
        submission_data = {
            "name": f"Test date {stamp}",
            "description": "Test filtering date",
            "dateCreated": datetime.strptime(stamp, format).timestamp(),
            "projectId": project_id,
        }
        submissions.append(await create_submission(database, submission_data))

    async with sess.get(
        f"{submissions_url}?date_created_start=2015-01-01&date_created_end=2015-12-31&projectId={project_id}"
    ) as resp:
        ans = await resp.json()
        assert resp.status == 200, f"returned status {resp.status}, error {ans}"
        assert ans["page"]["totalSubmissions"] == 2, f'Shold be 2 returned {ans["page"]["totalSubmissions"]}'

    # Test dateCreated within a month
    # Create submissions with different dateCreated
    timestamps = ["2013-01-31 00:00:00", "2013-02-02 00:00:00", "2013-03-29 00:00:00", "2013-04-01 00:00:00"]
    for stamp in timestamps:
        submission_data = {
            "name": f"Test date {stamp}",
            "description": "Test filtering date",
            "dateCreated": datetime.strptime(stamp, format).timestamp(),
            "projectId": project_id,
        }
        submissions.append(await create_submission(database, submission_data))

    async with sess.get(
        f"{submissions_url}?date_created_start=2013-02-01&date_created_end=2013-03-30&projectId={project_id}"
    ) as resp:
        ans = await resp.json()
        assert resp.status == 200, f"returned status {resp.status}, error {ans}"
        assert ans["page"]["totalSubmissions"] == 2, f'Shold be 2 returned {ans["page"]["totalSubmissions"]}'

    # Test dateCreated within a day
    # Create submissions with different dateCreated
    timestamps = [
        "2012-01-14 23:59:59",
        "2012-01-15 00:00:01",
        "2012-01-15 23:59:59",
        "2012-01-16 00:00:01",
    ]
    for stamp in timestamps:
        submission_data = {
            "name": f"Test date {stamp}",
            "description": "Test filtering date",
            "dateCreated": datetime.strptime(stamp, format).timestamp(),
            "projectId": project_id,
        }
        submissions.append(await create_submission(database, submission_data))

    async with sess.get(
        f"{submissions_url}?date_created_start=2012-01-15&date_created_end=2012-01-15&projectId={project_id}"
    ) as resp:
        ans = await resp.json()
        assert resp.status == 200, f"returned status {resp.status}, error {ans}"
        assert ans["page"]["totalSubmissions"] == 2, f'Shold be 2 returned {ans["page"]["totalSubmissions"]}'

    # Test parameters date_created_... and name together
    async with sess.get(
        f"{submissions_url}?name=2013&date_created_start=2012-01-01&date_created_end=2016-12-31&projectId={project_id}"
    ) as resp:
        ans = await resp.json()
        assert resp.status == 200, f"returned status {resp.status}, error {ans}"
        assert ans["page"]["totalSubmissions"] == 4, f'Shold be 4 returned {ans["page"]["totalSubmissions"]}'

    for submission in submissions:
        await delete_submission(sess, submission)


async def test_getting_submissions_filtered_by_date_modified(sess, database, project_id):
    """Check that /submissions returns submissions filtered by date modified.

    :param sess: HTTP session in which request call is made
    :param project_id: id of the project the submission belongs to
    """
    submissions = []
    format = "%Y-%m-%d %H:%M:%S"

    # Test lastModified within a year
    # Create submissions with different lastModified
    timestamps = ["2014-12-31 00:00:00", "2015-01-01 00:00:00", "2015-07-15 00:00:00", "2016-01-01 00:00:00"]
    for stamp in timestamps:
        submission_data = {
            "name": f"Test date {stamp}",
            "description": "Test filtering date",
            "lastModified": datetime.strptime(stamp, format).timestamp(),
            "projectId": project_id,
        }
        submissions.append(await create_submission(database, submission_data))

    async with sess.get(
        f"{submissions_url}?date_modified_start=2015-01-01&date_modified_end=2015-12-31&projectId={project_id}"
    ) as resp:
        ans = await resp.json()
        assert resp.status == 200, f"returned status {resp.status}, error {ans}"
        assert ans["page"]["totalSubmissions"] == 2, f'Shold be 2 returned {ans["page"]["totalSubmissions"]}'

    # Test lastModified within a month
    # Create submissions with different lastModified
    timestamps = ["2013-01-31 00:00:00", "2013-02-02 00:00:00", "2013-03-29 00:00:00", "2013-04-01 00:00:00"]
    for stamp in timestamps:
        submission_data = {
            "name": f"Test date {stamp}",
            "description": "Test filtering date",
            "lastModified": datetime.strptime(stamp, format).timestamp(),
            "projectId": project_id,
        }
        submissions.append(await create_submission(database, submission_data))

    async with sess.get(
        f"{submissions_url}?date_modified_start=2013-02-01&date_modified_end=2013-03-30&projectId={project_id}"
    ) as resp:
        ans = await resp.json()
        assert resp.status == 200, f"returned status {resp.status}, error {ans}"
        assert ans["page"]["totalSubmissions"] == 2, f'Shold be 2 returned {ans["page"]["totalSubmissions"]}'

    # Test lastModified within a day
    # Create submissions with different lastModified
    timestamps = [
        "2012-01-14 23:59:59",
        "2012-01-15 00:00:01",
        "2012-01-15 23:59:59",
        "2012-01-16 00:00:01",
    ]
    for stamp in timestamps:
        submission_data = {
            "name": f"Test date {stamp}",
            "description": "Test filtering date",
            "lastModified": datetime.strptime(stamp, format).timestamp(),
            "projectId": project_id,
        }
        submissions.append(await create_submission(database, submission_data))

    async with sess.get(
        f"{submissions_url}?date_modified_start=2012-01-15&date_modified_end=2012-01-15&projectId={project_id}"
    ) as resp:
        ans = await resp.json()
        assert resp.status == 200, f"returned status {resp.status}, error {ans}"
        assert ans["page"]["totalSubmissions"] == 2, f'Shold be 2 returned {ans["page"]["totalSubmissions"]}'

    # Test parameters date_created_... and name together
    async with sess.get(
        f"{submissions_url}?name=2013&date_modified_start=2012-01-01&"
        f"date_modified_end=2016-12-31&projectId={project_id}"
    ) as resp:
        ans = await resp.json()
        assert resp.status == 200, f"returned status {resp.status}, error {ans}"
        assert ans["page"]["totalSubmissions"] == 4, f'Shold be 4 returned {ans["page"]["totalSubmissions"]}'

    for submission in submissions:
        await delete_submission(sess, submission)


async def test_crud_users_works(sess, project_id):
    """Test users REST API GET, PATCH and DELETE reqs.

    :param sess: HTTP session in which request call is made
    :param project_id: id of the project the submission belongs to
    """
    # Check user exists in database (requires an user object to be mocked)
    async with sess.get(f"{users_url}/{user_id}") as resp:
        LOG.debug(f"Reading user {user_id}")
        assert resp.status == 200, f"HTTP Status code error, got {resp.status}"

    # Add user to session and create a patch to add submission to user
    submission_not_published = {
        "name": "Mock User Submission",
        "description": "Mock submission for testing users",
        "projectId": project_id,
    }
    submission_id = await post_submission(sess, submission_not_published)

    async with sess.get(f"{submissions_url}/{submission_id}?projectId={project_id}") as resp:
        LOG.debug(f"Checking that submission {submission_id} was added")
        res = await resp.json()
        assert res["name"] == submission_not_published["name"]
        assert res["projectId"] == submission_not_published["projectId"]

    submission_published = {
        "name": "Another test Submission",
        "description": "Test published submission does not get deleted",
        "projectId": project_id,
    }
    publish_submission_id = await post_submission(sess, submission_published)

    # Add DOI for publishing the submission
    doi_data_raw = await create_request_json_data("doi", "test_doi.json")
    await put_submission_doi(sess, publish_submission_id, doi_data_raw)

    dac_data = await create_request_json_data("dac", "dac_rems.json")
    await put_submission_dac(sess, publish_submission_id, dac_data)

    # add a study and dataset for publishing a submission
    await post_object_json(sess, "study", publish_submission_id, "SRP000539.json")
    await post_object(sess, "dataset", publish_submission_id, "dataset.xml")

    await publish_submission(sess, publish_submission_id)
    async with sess.get(f"{submissions_url}/{publish_submission_id}?projectId={project_id}") as resp:
        LOG.debug(f"Checking that submission {publish_submission_id} was published")
        res = await resp.json()
        assert res["published"] is True, "submission is not published, expected True"

    submission_not_published = {
        "name": "Delete Submission",
        "description": "Mock submission to delete while testing users",
        "projectId": project_id,
    }
    delete_submission_id = await post_submission(sess, submission_not_published)
    async with sess.get(f"{submissions_url}/{delete_submission_id}?projectId={project_id}") as resp:
        LOG.debug(f"Checking that submission {delete_submission_id} was added")
        res = await resp.json()
        assert res["name"] == submission_not_published["name"]
        assert res["projectId"] == submission_not_published["projectId"]
    await delete_submission(sess, delete_submission_id)
    async with sess.get(f"{submissions_url}/{delete_submission_id}?projectId={project_id}") as resp:
        LOG.debug(f"Checking that submission {delete_submission_id} was deleted")
        assert resp.status == 404

    template_id = await post_template_json(sess, "study", "SRP000539_template.json", project_id)
    await patch_template(sess, "study", template_id, "patch.json")
    async with sess.get(f"{templates_url}/study/{template_id}") as resp:
        LOG.debug(f"Checking that template: {template_id} was added")
        res = await resp.json()
        assert res["accessionId"] == template_id
        assert res["projectId"] == project_id
        assert res["identifiers"]["primaryId"] == "SRP000539"

    async with sess.get(f"{templates_url}?projectId={project_id}") as resp:
        LOG.debug("Checking that template display title was updated in separate templates list")
        res = await resp.json()
        assert res[0]["tags"]["displayTitle"] == "new name"

    await delete_template(sess, "study", template_id)
    async with sess.get(f"{templates_url}/study/{template_id}") as resp:
        LOG.debug(f"Checking that template {template_id} was deleted")
        assert resp.status == 404

    template_ids = await post_template_json(sess, "study", "SRP000539_list.json", project_id)
    assert len(template_ids) == 2, "templates could not be added as batch"
    templates = await get_templates(sess, project_id)

    assert len(templates) == 2, f"should be 2 templates, got {len(templates)}"
    assert templates[0]["schema"] == "template-study", "wrong template schema"

    # Delete user
    await delete_user(sess, user_id)
    # 401 means API is inaccessible thus session ended
    # this check is not needed but good to do
    async with sess.get(f"{users_url}/{user_id}") as resp:
        LOG.debug(f"Checking that user {user_id} was deleted")
        assert resp.status == 401, f"HTTP Status code error, got {resp.status}"


async def test_get_submissions(sess, submission_id: str, project_id: str):
    """Test submissions REST API GET .

    :param sess: HTTP session in which request call is made
    :param submission_id: id of the submission used to group submission objects
    :param project_id: id of the project the submission belongs to
    """
    async with sess.get(f"{submissions_url}?projectId={project_id}") as resp:
        LOG.debug(f"Reading submission {submission_id}")
        assert resp.status == 200, f"HTTP Status code error, got {resp.status}"
        response = await resp.json()
        LOG.error(response)
        assert len(response["submissions"]) == 1, len(response["submissions"])
        assert response["page"] == {"page": 1, "size": 5, "totalPages": 1, "totalSubmissions": 1}
        assert response["submissions"][0]["submissionId"] == submission_id


async def test_get_submissions_objects(sess, submission_id: str, project_id: str):
    """Test submissions REST API GET with objects.

    :param sess: HTTP session in which request call is made
    :param submission_id: id of the submission used to group submission objects
    :param project_id: id of the project the submission belongs to
    """
    accession_id = await post_object_json(sess, "study", submission_id, "SRP000539.json")
    async with sess.get(f"{submissions_url}?projectId={project_id}") as resp:
        LOG.debug(f"Reading submission {submission_id}")
        assert resp.status == 200, f"HTTP Status code error, got {resp.status}"
        response = await resp.json()
        assert len(response["submissions"]) == 1
        assert response["submissions"][0]["metadataObjects"][0]["accessionId"] == accession_id
        assert "tags" in response["submissions"][0]["metadataObjects"][0]
        assert response["submissions"][0]["metadataObjects"][0]["tags"]["submissionType"] == "Form"

    await delete_object(sess, "study", accession_id)


async def test_submissions_work(sess, submission_id):
    """Test actions in submission XML files.

    :param sess: HTTP session in which request call is made
    :param submission_id: id of the submission used to group submission objects
    """
    # Post original submission with two 'add' actions
    sub_files = [("submission", "ERA521986_valid.xml"), ("study", "SRP000539.xml"), ("sample", "SRS001433.xml")]
    submission_data = await create_multi_file_request_data(sub_files)

    async with sess.post(f"{submit_url}", params={"submission": submission_id}, data=submission_data) as resp:
        LOG.debug("Checking initial submission worked")
        assert resp.status == 200, f"HTTP Status code error, got {resp.status}"
        res = await resp.json()
        assert len(res) == 2, "expected 2 objects"
        assert res[0]["schema"] == "study", "expected first element to be study"
        assert res[1]["schema"] == "sample", "expected second element to be sample"
        study_access_id = res[0]["accessionId"]
        sample_access_id = res[1]["accessionId"]

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
        metax_id = res.get("metaxIdentifier", None)
        doi = res.get("doi", None)
        assert metax_id is not None
        assert doi is not None

    # check that objects are added to submission
    async with sess.get(f"{submissions_url}/{submission_id}") as resp:
        LOG.debug(f"Checking that submission {submission_id} was patched")
        res = await resp.json()
        expected_study = {
            "accessionId": study_access_id,
            "schema": "study",
            "tags": {
                "submissionType": "XML",
                "displayTitle": (
                    "Highly integrated epigenome maps in Arabidopsis - whole genome shotgun bisulfite sequencing"
                ),
                "fileName": "SRP000539.xml",
            },
        }
        assert expected_study in res["metadataObjects"], "submission metadataObjects content mismatch"
        expected_sample = {
            "accessionId": sample_access_id,
            "schema": "sample",
            "tags": {
                "submissionType": "XML",
                "displayTitle": "HapMap sample from Homo sapiens",
                "fileName": "SRS001433.xml",
            },
        }
        assert expected_sample in res["metadataObjects"], "submission metadataObjects content mismatch"

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
        assert res["metaxIdentifier"] == metax_id
        assert res["doi"] == doi

    # check that study is updated to submission
    async with sess.get(f"{submissions_url}/{submission_id}") as resp:
        LOG.debug(f"Checking that submission {submission_id} was patched")
        res = await resp.json()
        expected_study = {
            "accessionId": study_access_id,
            "schema": "study",
            "tags": {
                "submissionType": "XML",
                "displayTitle": "Different title for testing purposes",
                "fileName": "SRP000539_modified.xml",
            },
        }
        assert expected_study in res["metadataObjects"], "submission metadataObjects content mismatch"

    await delete_object(sess, "sample", sample_access_id)
    await delete_object(sess, "study", study_access_id)

    # Remove the accession id that was used for testing from test file
    LOG.debug("Sharing the correct accession ID created in this test instance")
    mod_study = testfiles_root / "study" / "SRP000539_modified.xml"
    tree = ET.parse(mod_study)
    root = tree.getroot()
    for elem in root.iter("STUDY"):
        del elem.attrib["accession"]
    tree.write(mod_study, encoding="utf-8")


async def test_minimal_json_publication(sess, project_id):
    """Test minimal publication workflow with json submissions.

    :param sess: HTTP session in which request call is made
    :param project_id: id of the project the submission belongs to
    """
    submission = {
        "name": "Minimal json publication",
        "description": "Testing json publication with new doi endpoint",
        "projectId": project_id,
    }
    submission_id = await post_submission(sess, submission)

    await post_object_json(sess, "study", submission_id, "SRP000539.json")
    doi_data_raw = await create_request_json_data("doi", "test_doi.json")
    await put_submission_doi(sess, submission_id, doi_data_raw)
    dac_data = await create_request_json_data("dac", "dac_rems.json")
    await put_submission_dac(sess, submission_id, dac_data)
    await publish_submission(sess, submission_id)

    async with sess.get(f"{submissions_url}/{submission_id}") as resp:
        LOG.debug(f"Checking that submission {submission_id} was published")
        res = await resp.json()
        assert res["submissionId"] == submission_id, "expected submission id does not match"
        assert res["published"] is True, "submission is published, expected False"


async def test_minimal_json_publication_rems(sess, project_id):
    """Test minimal publication workflow with json submissions.

    :param sess: HTTP session in which request call is made
    :param project_id: id of the project the submission belongs to
    """
    submission = {
        "name": "Minimal json publication",
        "description": "Testing json publication with new doi endpoint",
        "projectId": project_id,
    }
    submission_id = await post_submission(sess, submission)

    await post_object_json(sess, "study", submission_id, "SRP000539.json")
    ds_id = await post_object_json(sess, "dataset", submission_id, "dataset.json")

    doi_data_raw = await create_request_json_data("doi", "test_doi.json")
    await put_submission_doi(sess, submission_id, doi_data_raw)

    dac_data = await create_request_json_data("dac", "dac_rems.json")
    await put_submission_dac(sess, submission_id, dac_data)

    await publish_submission(sess, submission_id)

    async with sess.get(f"{submissions_url}/{submission_id}") as resp:
        LOG.debug(f"Checking that submission {submission_id} was published")
        res = await resp.json()
        assert res["submissionId"] == submission_id, "expected submission id does not match"
        assert res["published"] is True, "submission is published, expected False"

    async with sess.get(f"{objects_url}/dataset/{ds_id}?submission_id={submission_id}") as resp:
        LOG.debug(f"Checking that dataset {ds_id} in submission {submission_id} has rems data")
        res = await resp.json()
        assert res["accessionId"] == ds_id, "expected dataset id does not match"
        assert "dac" in res
        assert res["dac"]["workflowId"] == 1
        assert res["dac"]["organizationId"] == "CSC"
        assert "resourceId" in res["dac"]
        assert "catalogueId" in res["dac"]


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


async def main(url):
    """Launch different test tasks and run them."""
    mongo = Mongo(url)
    database = mongo.db

    async with aiohttp.ClientSession() as sess:

        LOG.debug("=== Login other mock user ===")
        await login(sess, other_test_user, other_test_user_given, other_test_user_family)
        user_data = await get_user_data(sess)
        project_id = user_data["projects"][0]["projectId"]

        # Test add, modify, validate and release action with submissions
        # added to validate that objects belong to a specific user
        LOG.debug("=== Testing actions within submissions ===")
        submission_submission = {
            "name": "submission test 1",
            "description": "submission test submission 1",
            "projectId": project_id,
        }
        submission_submission_id = await post_submission(sess, submission_submission)
        await test_get_submissions(sess, submission_submission_id, project_id)
        await test_get_submissions_objects(sess, submission_submission_id, project_id)
        await test_submissions_work(sess, submission_submission_id)

    async with aiohttp.ClientSession() as sess:
        LOG.debug("=== Login mock user ===")
        await login(sess, test_user, test_user_given, test_user_family)
        user_data = await get_user_data(sess)
        project_id = user_data["projects"][0]["projectId"]

        # Test adding and getting objects
        LOG.debug("=== Testing basic CRUD operations ===")
        basic_submission = {
            "name": "basic test",
            "description": "basic test submission",
            "projectId": project_id,
        }
        basic_submission_id = await post_submission(sess, basic_submission)

        # test XML files
        for schema, file in test_xml_files:
            await test_crud_works(sess, schema, file, basic_submission_id)
        await test_crud_with_multi_xml(sess, basic_submission_id)

        # test CSV files
        await test_csv(sess, basic_submission_id)

        put_object_submission = {
            "name": "test put object",
            "description": "put object test submission",
            "projectId": project_id,
        }
        put_object_submission = await post_submission(sess, put_object_submission)

        await test_put_objects(sess, put_object_submission)

        # Test adding and getting draft objects
        LOG.debug("=== Testing basic CRUD drafts operations ===")
        draft_submission = {
            "name": "basic test draft",
            "description": "basic test draft submission",
            "projectId": project_id,
        }
        draft_submission_id = await post_submission(sess, draft_submission)

        for schema, file, file2 in test_json_files:
            await test_crud_drafts_works(sess, schema, file, file2, draft_submission_id)

        # Test patch and put
        LOG.debug("=== Testing patch and put drafts operations ===")
        await test_crud_drafts_works(sess, "sample", "SRS001433.json", "put.json", draft_submission_id)
        await test_patch_drafts_works(sess, "study", "SRP000539.json", "patch.json", draft_submission_id)

        # Test queries
        LOG.debug("=== Testing queries ===")
        query_submission = {
            "name": "basic test query",
            "description": "basic test query submission",
            "projectId": project_id,
        }
        query_submission_id = await post_submission(sess, query_submission)
        await test_querying_works(sess, query_submission_id)

        # Test /objects/study endpoint for query pagination
        LOG.debug("=== Testing getting all objects & pagination ===")
        pagination_submission = {
            "name": "basic test pagination",
            "description": "basic test pagination submission",
            "projectId": project_id,
        }
        pagination_submission_id = await post_submission(sess, pagination_submission)
        await test_getting_all_objects_from_schema_works(sess, pagination_submission_id)

        # Test creating, reading, updating and deleting submissions
        LOG.debug("=== Testing basic CRUD submission operations ===")
        await test_crud_submissions_works(sess, project_id)
        await test_crud_submissions_works_no_publish(sess, project_id)
        await test_adding_doi_info_to_submission_works(sess, project_id)

        # Test creating a submission, with minimal required objects + DOI for publishing
        LOG.debug("=== Testing minimal JSON submission ===")
        await test_minimal_json_publication(sess, project_id)

        LOG.debug("=== Testing minimal JSON submission with REMS integration ===")
        await test_minimal_json_publication_rems(sess, project_id)

        # Test getting a list of submissions and draft templates owned by the user
        LOG.debug("=== Testing getting submissions, draft submissions and draft templates with pagination ===")
        await test_getting_paginated_submissions(sess, project_id)
        LOG.debug("=== Testing getting submissions filtered with name and date created ===")
        await test_getting_submissions_filtered_by_name(sess, project_id)
        await test_getting_submissions_filtered_by_date_created(sess, database, project_id)
        await test_getting_submissions_filtered_by_date_modified(sess, database, project_id)

        # Test objects study and dataset are connecting to metax and saving metax id to db
        LOG.debug("=== Testing Metax integration related basic CRUD operations for study and dataset ===")
        metax_submission = {
            "name": "Metax testing submission",
            "description": "Metax crud testing submission",
            "projectId": project_id,
        }
        metax_submission_id = await post_submission(sess, metax_submission)
        await test_metax_crud_with_xml(sess, metax_submission_id)
        await test_metax_crud_with_json(sess, metax_submission_id)
        await test_metax_id_not_updated_on_patch(sess, metax_submission_id)
        await test_metax_publish_dataset(sess, metax_submission_id)
        metax_submission = {
            "name": "Metax testing publishing submission",
            "description": "Metax publishing testing submission",
            "projectId": project_id,
        }
        metax_submission_id = await post_submission(sess, metax_submission)
        await test_metax_publish_dataset_with_missing_metax_id(sess, database, metax_submission_id)

        # Test add, modify, validate and release action with submissions
        LOG.debug("=== Testing actions within submissions ===")
        submission_submission = {
            "name": "submission test",
            "description": "submission test submission",
            "projectId": project_id,
        }
        submission_submission_id = await post_submission(sess, submission_submission)
        await test_submissions_work(sess, submission_submission_id)

        # Test health status check
        LOG.debug("=== Testing health status check ===")
        await test_health_check(sess)

        # Test reading, updating and deleting users
        # this needs to be done last as it deletes users
        LOG.debug("=== Testing basic CRUD user operations ===")
        await test_crud_users_works(sess, project_id)


async def clear_metax_cache():
    """Clear metax cache."""
    async with aiohttp.ClientSession() as sess:
        await sess.post(f"{metax_url}/purge")


if __name__ == "__main__":
    if TLS:
        _params = "?tls=true&tlsCAFile=./config/cacert&tlsCertificateKeyFile=./config/combined"
        url = f"mongodb://{AUTHDB}:{AUTHDB}@{HOST}/{DATABASE}{_params}&authSource=admin"
    else:
        url = f"mongodb://{AUTHDB}:{AUTHDB}@{HOST}/{DATABASE}?authSource=admin"

    try:
        asyncio.run(Mongo(url).recreate_db())
        asyncio.run(main(url))
    finally:
        # Clean up after tests are done
        LOG.info("Cleaning up DB")
        asyncio.run(Mongo(url).drop_db())
        asyncio.run(clear_metax_cache())
