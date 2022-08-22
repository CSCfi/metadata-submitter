"""Helper functions for the integration tests."""
import json
import logging
import re
from urllib.parse import urlencode
from uuid import uuid4

import aiofiles
from aiohttp import FormData

from .conf import (
    base_url,
    drafts_url,
    metax_api,
    mock_auth_url,
    objects_url,
    publish_url,
    submissions_url,
    templates_url,
    testfiles_root,
    users_url,
)

LOG = logging.getLogger(__name__)
LOG.setLevel(logging.DEBUG)


async def login(sess, sub, given, family):
    """Mock login."""
    params = {
        "sub": sub,
        "family": family,
        "given": given,
    }

    # Prepare response
    url = f"{mock_auth_url}/setmock?{urlencode(params)}"
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
    async with sess.post(
        f"{objects_url}/{schema}",
        params={"submission": submission_id},
        data=request_data,
    ) as resp:
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
    async with sess.post(
        f"{objects_url}/{schema}",
        params={"submission": submission_id},
        data=request_data,
    ) as resp:
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
    async with sess.post(
        f"{objects_url}/{schema}",
        params={"submission": submission_id},
        data=request_data,
    ) as resp:
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
    async with sess.post(
        f"{objects_url}/{schema}",
        params={"submission": submission_id},
        data=request_data,
    ) as resp:
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
    async with sess.post(
        f"{drafts_url}/{schema}",
        params={"submission": submission_id},
        data=request_data,
    ) as resp:
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
    async with sess.post(
        f"{drafts_url}/{schema}",
        params={"submission": submission_id},
        data=request_data,
    ) as resp:
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
        await sess.delete(f"{metax_api}/{metax_id}")
    except Exception as e:
        LOG.error(f"Object deletion from mocked Metax failed due to {str(e)}")


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
