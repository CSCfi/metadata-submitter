"""Helper functions for the integration tests."""

import json
import logging
import re
from urllib.parse import urlencode
from uuid import uuid4

import aiofiles
import aiohttp
import ujson
from aiohttp import FormData

from .conf import (
    admin_url,
    announce_url,
    base_url,
    drafts_url,
    files_url,
    metax_api,
    mock_auth_url,
    objects_url,
    publish_url,
    submissions_url,
    taxonomy_url,
    testfiles_root,
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


async def get_request_data(schema, filename) -> str:
    """Get request data from a test file.

    :param schema: name of the schema.
    :param filename: name of the test file.
    :return: Contents of the test file.
    """
    path_to_file = testfiles_root / schema / filename
    path = path_to_file.as_posix()
    async with aiofiles.open(path, mode="r") as f:
        return await f.read()


async def get_object(sess, schema, accession_id):
    """Get one metadata object within session, returns object's data.

    :param sess: HTTP session in which request call is made
    :param schema: name of the schema (submission) used for testing
    :param accession_id: object to fetch
    :returns: data of an object
    """
    async with sess.get(f"{objects_url}/{schema}/{accession_id}") as resp:
        LOG.debug("Getting object from %s with %s", schema, accession_id)
        data = await resp.json()
        assert resp.status == 200, f"HTTP Status code error, got {resp.status}"
        return data


async def get_xml_object(sess, schema, accession_id):
    """Get the XML content of one metadata object.

    :param sess: HTTP session in which request call is made
    :param schema: name of the schema (submission) used for testing
    :param accession_id: object to fetch
    :returns: data of an object
    """
    async with sess.get(f"{objects_url}/{schema}/{accession_id}?format=xml") as resp:
        LOG.debug("Getting xml object from %s with %s", schema, accession_id)
        assert resp.status == 200, f"HTTP Status code error, got {resp.status}"
        data = await resp.text()
        return data


async def post_object(sess, schema, submission_id, filename) -> str | None:
    """Post one XML or JSON metadata object within session, returns accessionId.

    :param sess: HTTP session in which request call is made
    :param schema: name of the schema (submission) used for testing
    :param submission_id: submission object belongs to
    :param filename: name of the file used for testing.
    :returns: accessionId of created object
    """
    LOG.debug(f"Adding new {schema} object from file {filename}")
    data = await get_request_data(schema, filename)
    return await post_object_data(sess, schema, submission_id, data)


async def post_object_data(sess, schema, submission_id, data) -> str | None:
    """Post one XML or JSON metadata object within session, returns accessionId.

    :param sess: HTTP session in which request call is made
    :param schema: name of the schema (submission) used for testing
    :param submission_id: submission object belongs to
    :param data: the metadata object data
    :returns: accessionId of created object
    """
    async with sess.post(
            f"{objects_url}/{schema}",
            params={"submission": submission_id},
            data=data,
    ) as resp:
        response = await resp.json()
        LOG.debug(f"Adding new {schema} object")
        assert resp.status == 201, f"HTTP Status code error, got {resp.status}"

        if schema == "bprems":
            return None
        return (response[0] if isinstance(response, list) else response)["accessionId"]


async def post_multi_object(sess, schema, submission_id, filename) -> list[str]:
    """Post multiple metadata objects. Returns list of object accessions.

    :param sess: HTTP session in which request call is made
    :param schema: name of the schema (submission) used for testing
    :param submission_id: submission object belongs to
    :param filename: name of the file used for testing.
    :returns: response data after created objects
    """
    request_data = await get_request_data(schema, filename)
    async with sess.post(
            f"{objects_url}/{schema}",
            params={"submission": submission_id},
            data=request_data,
    ) as resp:
        LOG.debug("Posting  %s objects from file %s", schema, filename)
        assert resp.status == 201, f"HTTP Status code error, got {resp.status}"
        return [r["accessionId"] for r in await resp.json()]


async def delete_object(sess, schema, accession_id):
    """Delete metadata object within session.

    :param sess: HTTP session in which request call is made
    :param schema: name of the schema (submission) used for testing
    :param accession_id: id of the object
    """
    async with sess.delete(f"{objects_url}/{schema}/{accession_id}") as resp:
        LOG.debug("Deleting object %s from %s", accession_id, schema)
        assert resp.status == 204, f"HTTP Status code error, got {resp.status}"


async def post_draft(sess, schema, submission_id, filename):
    """Post one draft XML or JSON metadata object within session, returns accessionId.

    :param sess: HTTP session in which request call is made
    :param schema: name of the schema (submission) used for testing
    :param submission_id: submission object belongs to
    :param filename: name of the file used for testing.
    :returns: accessionId of created draft
    """
    request_data = await get_request_data(schema, filename)
    async with sess.post(
            f"{drafts_url}/{schema}",
            params={"submission": submission_id},
            data=request_data,
    ) as resp:
        LOG.debug("Adding new draft object to %s, via XML file %s", schema, filename)
        assert resp.status == 201, f"HTTP Status code error, got {resp.status}"
        response = await resp.json()
        return (response[0] if isinstance(response, list) else response)["accessionId"]


async def get_draft(sess, schema, draft_id, expected_status=200):
    """Get and return a drafted metadata object.

    :param sess: HTTP session in which request call is made
    :param schema: name of the schema (submission) used for testing
    :param draft_id: id of the draft
    :param expected_status: HTTP status to expect for
    :returns: data of a draft
    """
    async with sess.get(f"{drafts_url}/{schema}/{draft_id}") as resp:
        LOG.debug("Checking that %s draft exists", draft_id)
        assert resp.status == expected_status, f"HTTP Status code error, got {resp.status}"
        ans = await resp.json()
        return json.dumps(ans)


async def put_draft(sess, schema, draft_id, update_filename):
    """Put one metadata object within session, returns accessionId.

    :param sess: HTTP session in which request call is made
    :param schema: name of the schema (submission) used for testing
    :param draft_id: id of the draft
    :param update_filename: name of the file used to use for updating data.
    :returns: accession id of updated draft
    """
    request_data = await get_request_data(schema, update_filename)
    async with sess.put(f"{drafts_url}/{schema}/{draft_id}", data=request_data) as resp:
        LOG.debug("Replace draft object in %s", schema)
        assert resp.status == 200, f"HTTP Status code error, got {resp.status}"
        ans_put = await resp.json()
        assert ans_put["accessionId"] == draft_id, "accession ID error"
        return ans_put["accessionId"]


async def put_object(sess, schema, accession_id, update_filename):
    """Put one JSON or XML metadata object within session.

    :param sess: HTTP session in which request call is made
    :param schema: name of the schema (submission) used for testing
    :param accession_id: id of the object
    :param update_filename: name of the file used to use for updating data.
    """
    request_data = await get_request_data(schema, update_filename)
    async with sess.put(f"{objects_url}/{schema}/{accession_id}", data=request_data) as resp:
        LOG.debug("Put %s metadata object", schema)
        assert resp.status == 200, f"HTTP Status code error, got {resp.status}"


async def patch_object(sess, schema, accession_id, update_filename):
    """Patch one JSON or XML metadata object within session.

    :param sess: HTTP session in which request call is made
    :param schema: name of the schema (submission) used for testing
    :param accession_id: id of the object
    :param update_filename: name of the file used to use for updating data.
    :returns: accession id of updated object
    """
    request_data = await get_request_data(schema, update_filename)
    async with sess.patch(f"{objects_url}/{schema}/{accession_id}", data=request_data) as resp:
        LOG.debug("Patch %s metadata object", schema)
        assert resp.status == 200, f"HTTP Status code error, got {resp.status}"


async def patch_draft(sess, schema, draft_id, update_filename):
    """Patch one metadata object within session, return accessionId.

    :param sess: HTTP session in which request call is made
    :param schema: name of the schema (submission) used for testing
    :param draft_id: id of the draft
    :param update_filename: name of the file used to use for updating data.
    :returns: accession id of updated draft
    """
    request_data = await get_request_data(schema, update_filename)
    async with sess.patch(f"{drafts_url}/{schema}/{draft_id}", data=request_data) as resp:
        LOG.debug("Update draft object in %s", schema)
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
        LOG.debug("Deleting draft object %s from %s", draft_id, schema)
        assert resp.status == 204, f"HTTP Status code error, got {resp.status}"


async def post_submission(sess, data):
    """Post one object submission within session, returns submissionId.

    :param sess: HTTP session in which request call is made
    :param data: data used to update the submission
    """
    async with sess.post(f"{submissions_url}", data=json.dumps(data)) as resp:
        ans = await resp.json()
        assert resp.status == 201, f"HTTP Status code error {resp.status} {ans}"
        LOG.debug("Adding new submission %s", ans["submissionId"])
        return ans["submissionId"]


async def patch_submission(sess, submission_id, data):
    """Patch one object submission within session, return submissionId.

    :param sess: HTTP session in which request call is made
    :param submission_id: id of the submission
    :param data: JSON object to use in PATCH call
    """
    async with sess.patch(f"{submissions_url}/{submission_id}", data=json.dumps(data)) as resp:
        LOG.debug("Updating submission %s", submission_id)
        assert resp.status == 200, f"HTTP Status code error, got {resp.status}"
        ans_patch = await resp.json()
        assert ans_patch["submissionId"] == submission_id, "submission ID error"
        return ans_patch["submissionId"]


async def publish_submission(sess, submission_id, *, no_files: bool = True):
    """Publish one object submission within session, return submissionId.

    :param sess: HTTP session in which request call is made
    :param submission_id: id of the submission
    """
    async with sess.patch(f"{publish_url}/{submission_id}?no_files=true") as resp:
        LOG.debug("Publishing submission %s", submission_id)
        result = await resp.json()
        assert resp.status == 200, f"HTTP Status code error, got {resp.status}: {result}"
        assert result["submissionId"] == submission_id, "submission ID error"
        return result["submissionId"]


async def delete_submission(sess, submission_id,
                            ignore_published_error: bool = False,
                            ignore_not_found_error: bool = False):
    """Delete submission.

    :param sess: HTTP session in which request call is made
    :param submission_id: id of the submission
    :param ignore_published_error: ignore error when submission has been published and can't be deleted
    :param ignore_not_found_error: ignore error when submission does not exist
    """
    async with sess.delete(f"{submissions_url}/{submission_id}") as resp:
        LOG.debug("Deleting submission %s", submission_id)
        result = await resp.text()
        assert resp.status == 204 or (
                resp.status == 400 and ignore_published_error and "has been published" in result
        ) or (resp.status == 404 and ignore_not_found_error)


async def delete_published_submission(sess, submission_id, *, expected_status=405):
    """Delete object submission within session unsuccessfully because it's already published.

    :param sess: HTTP session in which request call is made
    :param submission_id: id of the submission
    """
    async with sess.delete(f"{submissions_url}/{submission_id}") as resp:
        LOG.debug("Deleting submission %s", submission_id)
        assert resp.status == expected_status, f"HTTP Status code error, got {resp.status}"


async def patch_submission_doi(sess, submission_id, data):
    """Patch doi into submission within session, returns submissionId.

    :param sess: HTTP session in which request call is made
    :param submission_id: id of the submission
    :param data: doi data used to update the submission
    :returns: Submission id for the submission inserted to database
    """
    async with sess.patch(f"{submissions_url}/{submission_id}/doi", data=data) as resp:
        ans = await resp.json()
        assert resp.status == 200, f"HTTP Status code error {resp.status} {ans}"
        LOG.debug("Adding doi to submission %s", ans["submissionId"])
        return ans["submissionId"]


async def patch_submission_rems(sess, submission_id, data):
    """Patch REMS (DAC) into submission within session, returns submissionId.

    :param sess: HTTP session in which request call is made
    :param submission_id: id of the submission
    :param data: REMS data used to update the submission
    :returns: Submission id for the submission inserted to database
    """
    async with sess.patch(f"{submissions_url}/{submission_id}/rems", data=data) as resp:
        ans = await resp.json()
        assert resp.status == 200, f"HTTP Status code error {resp.status} {ans}"
        LOG.debug("Adding REMS DAC to submission %s", ans["submissionId"])
        return ans["submissionId"]


async def create_submission(database, data):
    """Create new object submission to database.

    :param database: database client to perform db operations
    :param data: Data as dict to be saved to database
    :returns: Submission id for the submission inserted to database
    """
    submission_id = uuid4().hex
    LOG.info("Creating new submission %s", submission_id)
    data["submissionId"] = submission_id
    data["text_name"] = " ".join(re.split("[\\W_]", data["name"]))
    data["drafts"] = []
    data["metadataObjects"] = []
    try:
        await database["submission"].insert_one(data)
        return submission_id

    except Exception as e:
        LOG.exception("Submission creation failed due to %s", str(e))


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
        LOG.exception("Object update failed due to %s", str(e))
    try:
        await sess.delete(f"{metax_api}/{metax_id}")
    except Exception as e:
        LOG.exception("Object deletion from mocked Metax failed due to %s", str(e))


async def check_object_exists(sess, schema, accession_id, draft=False):
    """Check that the metadata object is added to submission.

    :param sess: HTTP session in which request call is made
    :param schema: name of the schema (submission) used for testing
    :param accession_id: accession ID of metadata object
    :param draft: indication of object draft status, default False
    """
    if draft:
        await get_draft(sess, schema, accession_id)
    else:
        await get_object(sess, schema, accession_id)


async def post_project_files(sess, file_data, is_bigpicture=""):
    """Post files within session, returns created file ids.

    :param sess: HTTP session in which request call is made
    :param file_data: new file data containing userId, projectId, file info
    :param is_bigpicture: specify if the file belongs to Bigpicture
    :returns: list of file ids of created files
    """
    params = {"is_bigpicture": is_bigpicture}
    async with sess.post(files_url, data=ujson.dumps(file_data), params=params) as resp:
        ans = await resp.json()
        assert resp.status == 201, f"HTTP Status code error, got {resp.status}: {ans}"
        return ans


async def get_project_files(sess, project_id: str):
    """Get files within session.

    :param sess: HTTP session in which request call is made
    :param project_id: project ID where the file belongs to
    :returns: list of files
    """
    params = {"projectId": project_id}
    async with sess.get(files_url, params=params) as resp:
        ans = await resp.json()
        assert resp.status == 200, f"HTTP Status code error, got {resp.status}: {ans}"
        return ans


async def find_project_file(sess, projectId, fileId):
    """Check if file with the given id is in project files.

    :param sess: HTTP session in which request call is made
    :param projectId: id of project to find a file in
    :param fileId: id of file to find
    :returns: boolean
    """
    params = {"projectId": projectId}

    async with sess.get(files_url, params=params) as resp:
        ans = await resp.json()
        assert resp.status == 200, f"HTTP Status code error {resp.status} {ans}"

        for file in ans:
            if file["accessionId"] == fileId:
                return True

        return False


async def patch_submission_files(sess, file_data, submission_id):
    """Add or update files to an existing submission.

    :param sess: HTTP session in which request call is made
    :param file_data: details of files to add to a submission
    :param submission_id: id of submission to add files to
    """
    url = f"{submissions_url}/{submission_id}/files"

    async with sess.patch(url, data=ujson.dumps(file_data)) as resp:
        assert resp.status == 204, f"HTTP Status code error, got {resp.status}"


async def get_submission_files(sess, submission_id):
    """Get submission files.

    :param sess: HTTP session in which request call is made
    :param submission_id: The submission id
    """
    url = f"{submissions_url}/{submission_id}/files"
    async with sess.get(url) as resp:
        assert resp.status == 200, f"HTTP Status code error, got {resp.status}"
        result = await resp.json()
        return result


async def delete_submission_file(sess, submission_id, file_id):
    """Delete submission file.

    :param sess: HTTP session in which request call is made
    :param submission_id: The submission id
    :param file_id: The file id
    """
    url = f"{submissions_url}/{submission_id}/files/{file_id}"
    async with sess.delete(url) as resp:
        assert resp.status == 204, f"HTTP Status code error, got {resp.status}"


async def get_submission(sess, submission_id):
    """Get submission with the given id.

    :param sess: HTTP session in which request call is made
    :param submission_id: id of submission to return
    :returns: submission object
    """
    url = f"{submissions_url}/{submission_id}"

    async with sess.get(url) as resp:
        ans = await resp.json()
        assert resp.status == 200, f"HTTP Status code error {resp.status}"
        return ans


async def add_submission_linked_folder(sess, submission_id, name):
    """Add a linked folder name to a submission.

    :param sess: HTTP session in which request call is made
    :param submission_id: id of submission to add path to
    :param name: linked folder name string
    """
    data = {"linkedFolder": name}
    url = f"{submissions_url}/{submission_id}/folder"

    async with sess.patch(
            url,
            data=ujson.dumps(data),
    ) as resp:
        assert resp.status == 204, f"HTTP Status code error, got {resp.status}"


async def remove_submission_file(sess, submission_id, file_id):
    """Remove file from an existing submission.

    :param sess: HTTP session in which request call is made
    :param submission_id: id of submission the file of which to remove
    :param file_id: id of file to remove
    """
    url = f"{submissions_url}/{submission_id}/files/{file_id}"

    async with sess.delete(url) as resp:
        assert resp.status == 204, f"HTTP Status code error {resp.status}"


def generate_mock_file(name: str):
    """Generate mock file object for file POST testing.

    :param name: name for file
    :returns: file object
    """
    return {
        "name": f"{name}.c4gh",
        "path": f"s3:/bucket/mock_files/{name}.c4gh",
        "bytes": 100,
        "encrypted_checksums": [{"type": "md5", "value": "7Ac236b1a82dac89e7cf45d2b4812345"}],
        "unencrypted_checksums": [{"type": "md5", "value": "7Ac236b1a82dac89e7cf45d2b4812345"}],
    }


async def delete_project_files(sess, project_id, file_paths):
    """Remove file from an existing submission.

    :param sess: HTTP session in which request call is made
    :param project_id: project ID where the file belongs to
    :param file_paths: path of the file to be flagged as deleted
    """
    url = f"{files_url}/{project_id}"
    async with sess.delete(url, data=ujson.dumps(file_paths)) as resp:
        assert resp.status == 204, f"HTTP Status code error {resp.status}"


async def search_taxonomy(sess, query: str, max_results: int = 10):
    """Send a taxonomy name search query.

    :param sess: HTTP session in which request call is made
    :param query: string to query taxonomy for
    :param max_results: how many search results to display (Optional)
    """
    params = {"search": query}
    if max_results != 10:
        params["results"] = max_results

    url = f"{taxonomy_url}?{urlencode(params)}"

    async with sess.get(url) as resp:
        LOG.debug(resp)
        return await resp.json() if resp.status == 200 else resp


async def get_mock_admin_token(sess):
    """Get token from mock admin user.

    :param sess: HTTP session in which request call is made
    :returns: token
    """
    async with sess.post(f"{mock_auth_url}/token") as resp:
        assert resp.status == 200
        ans = await resp.json()
        id_token = ans.get("id_token")
        return id_token


async def setup_files_for_ingestion(sess, dataset_id, submission_id, user_id, project_id, id_token):
    """Create files for a BigPicture submission, and add them to the database, submission and inbox.

    :param sess: HTTP session in which request call is made
    :param dataset_id: Dataset accession ID
    :param submission_id: id of the submission
    :param user_id: ID of user
    :param project_id: project ID where the file belongs to
    :param id_token: Token for authorizing admin user
    """
    # Create files and add files to submission
    mock_file_1 = generate_mock_file("file10")
    mock_file_2 = generate_mock_file("file20")

    file_data = {
        "userId": user_id,
        "projectId": project_id,
        "files": [mock_file_1, mock_file_2],
    }

    created_files = await post_project_files(sess, file_data)
    submission_files = []
    for file in created_files:
        submission_files.append(
            {
                "accessionId": file["accessionId"],
                "version": file["version"],
                "objectId": {"accessionId": dataset_id, "schema": "bpdataset"},
            }
        )
    await patch_submission_files(sess, submission_files, submission_id)

    async with aiohttp.ClientSession(headers={"Authorization": "Bearer " + id_token}) as admin_client:
        await add_file_to_inbox(admin_client, mock_file_1["path"], user_id)
        await add_file_to_inbox(admin_client, mock_file_2["path"], user_id)


async def check_file_accession_ids(sess, files, username):
    """Check that accession IDs are added correctly to files in archive.

    :param sess: HTTP session in which request call is made
    :param files: List of files with their accession IDs and paths
    :param username: username of the user (current)
    """
    async with sess.get(f"{admin_url}/users/{username}/accessions") as resp:
        assert resp.status == 200, f"HTTP Status code error {resp.status}"
        ans = await resp.json()
        for file in files:
            assert ans[file["path"]] == file["accessionId"]


async def check_dataset_accession_ids(sess, files, dataset_id):
    """Check that the dataset has been created and assigned the correct file accession IDs.

    :param sess: HTTP session in which request call is made
    :param files: List of files with their accession IDs and paths
    :param dataset_id: Dataset accession ID
    """
    async with sess.get(url=f"{admin_url}/dataset/{dataset_id}") as resp:
        assert resp.status == 200, f"HTTP Status code error {resp.status}"
        ans = await resp.json()
        assert sorted(list(x["accessionId"] for x in files)) == sorted(ans["files"])


async def add_file_to_inbox(sess, filepath, username):
    """Add a new file to inbox via the Admin API.

    :param sess: HTTP session in which request call is made
    :param filepath: path of the file
    :param username: username of the user (current)
    """
    file_data = {"user": username, "filepath": filepath}
    async with sess.post(f"{admin_url}/file/create", json=file_data) as resp:
        assert resp.status == 201, f"HTTP Status code error {resp.status}"
