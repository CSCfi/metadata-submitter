"""Helper functions for the integration tests."""

import io
import json
import logging
import os
import re
from urllib.parse import urlencode
from uuid import uuid4

import aioboto3
import aiofiles
import ujson
from aiohttp import ClientSession

from metadata_backend.api.models import Submission, SubmissionWorkflow
from .conf import (
    admin_url,
    base_url,
    metax_api,
    mock_auth_url,
    mock_s3_region,
    mock_s3_url,
    objects_url,
    publish_url,
    submissions_url,
    taxonomy_url,
    testfiles_root, API_PREFIX,
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


async def submit_bp(sess, project_id: str) -> Submission:
    """
    Create a default BP submission and return the submission document.

    :return: The submission document.
    """

    submission_dir = testfiles_root / "xml" / "bp" / "submission_1"
    workflow = SubmissionWorkflow.BP.value
    files = [
        "dataset.xml",
        "policy.xml",
        "image.xml",
        "annotation.xml",
        "observation.xml",
        "observer.xml",
        "sample.xml",
        "staining.xml",
        "landing_page.xml",
        "rems.xml",
        "organisation.xml",
    ]

    # Read XML files.
    data = {}
    for file in files:
        data[file] = (submission_dir / file).open("rb")

    async with sess.post(
            f"{base_url}{API_PREFIX}/workflows/{workflow}/projects/{project_id}/submissions",
            data=data) as response:
        assert response.status == 200
        submission = Submission.model_validate(await response.json())
        return submission


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
    async with sess.patch(f"{publish_url}/{submission_id}?no_files={str(no_files).lower()}") as resp:
        LOG.debug("Publishing submission %s", submission_id)
        result = await resp.json()
        LOG.debug(result)
        assert resp.status == 200, f"HTTP Status code error, got {resp.status}: {result}"
        assert result["submissionId"] == submission_id, "submission ID error"
        return result["submissionId"]


async def delete_submission(
        sess, submission_id, ignore_published_error: bool = False, ignore_not_found_error: bool = False
):
    """Delete submission.

    :param sess: HTTP session in which request call is made
    :param submission_id: id of the submission
    :param ignore_published_error: ignore error when submission has been published and can't be deleted
    :param ignore_not_found_error: ignore error when submission does not exist
    """
    async with sess.delete(f"{submissions_url}/{submission_id}") as resp:
        LOG.debug("Deleting submission %s", submission_id)
        result = await resp.text()
        assert (
                resp.status == 204
                or (resp.status == 400 and ignore_published_error and "has been published" in result)
                or (resp.status == 404 and ignore_not_found_error)
        )


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


async def patch_submission_rems(sess, submission_id, data: str):
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


async def remove_submission_file(sess, submission_id, file_path):
    """Remove file from an existing submission.

    :param sess: HTTP session in which request call is made
    :param submission_id: id of submission the file of which to remove
    :param file_path: path of file to remove
    """
    url = f"{submissions_url}/{submission_id}/files/{file_path}"

    async with sess.delete(url) as resp:
        assert resp.status == 204, f"HTTP Status code error {resp.status}"


def generate_mock_file(filepath: str):
    """Generate mock file object for file POST testing.

    :param name: name for file
    :returns: file object
    """
    return {
        "filepath": filepath,
        "status": "added",
        "bytes": 100,
        "encrypted_checksums": [{"type": "md5", "value": "7Ac236b1a82dac89e7cf45d2b4812345"}],
        "unencrypted_checksums": [{"type": "md5", "value": "7Ac236b1a82dac89e7cf45d2b4812345"}],
    }


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
    submission_files = [
        {**generate_mock_file("file10"), "objectId": {"accessionId": dataset_id, "schema": "bpdataset"}},
        {**generate_mock_file("file20"), "objectId": {"accessionId": dataset_id, "schema": "bpdataset"}},
    ]
    await patch_submission_files(sess, submission_files, submission_id)

    async with ClientSession(headers={"Authorization": "Bearer " + id_token}) as admin_client:
        await add_file_to_inbox(admin_client, submission_files[0]["filepath"], user_id)
        await add_file_to_inbox(admin_client, submission_files[1]["filepath"], user_id)


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


async def add_file_to_folder(folder_name, object_key):
    """Add a new object to a mock S3 bucket.

    :param sess: HTTP session in which request call is made
    :param folder_name: name of the folder
    :param object_key: key for the object to be added
    """
    random_bytes = os.urandom(100)  # 100 bytes of random data
    file_obj = io.BytesIO(random_bytes)
    session = aioboto3.Session()
    async with session.client(
            "s3",
            endpoint_url=mock_s3_url,
            aws_access_key_id="test",
            aws_secret_access_key="test",
            region_name=mock_s3_region,
            use_ssl=False,
    ) as s3:
        await s3.upload_fileobj(file_obj, folder_name, object_key)


async def delete_file_from_folder(folder_name, object_key):
    """Delete an object from a mock S3 bucket.

    :param folder_name: name of the folder
    :param object_key: key for the object to be deleted
    """
    session = aioboto3.Session()
    async with session.client(
            "s3",
            endpoint_url=mock_s3_url,
            aws_access_key_id="test",
            aws_secret_access_key="test",
            region_name=mock_s3_region,
            use_ssl=False,
    ) as s3:
        await s3.delete_object(Bucket=folder_name, Key=object_key)


async def add_folder(folder_name):
    """Add a new folder (bucket) to a mock S3 service.

    :param folder_name: name of the folder
    """
    session = aioboto3.Session()
    async with session.client(
            "s3",
            endpoint_url=mock_s3_url,
            aws_access_key_id="test",
            aws_secret_access_key="test",
            region_name=mock_s3_region,
            use_ssl=False,
    ) as s3:
        await s3.create_bucket(Bucket=folder_name)


async def delete_folder(folder_name):
    """Delete a folder (bucket) from a mock S3 service.

    :param folder_name: name of the folder
    """
    session = aioboto3.Session()
    async with session.client(
            "s3",
            endpoint_url=mock_s3_url,
            aws_access_key_id="test",
            aws_secret_access_key="test",
            region_name=mock_s3_region,
            use_ssl=False,
    ) as s3:
        await s3.delete_bucket(Bucket=folder_name)


async def list_folders():
    """List all folders (buckets) in the mock S3 service."""
    session = aioboto3.Session()
    async with session.client(
            "s3",
            endpoint_url=mock_s3_url,
            aws_access_key_id="test",
            aws_secret_access_key="test",
            region_name=mock_s3_region,
            use_ssl=False,
    ) as s3:
        buckets = await s3.list_buckets()
        return [bucket["Name"] for bucket in buckets.get("Buckets", [])]


async def list_files_in_folder(folder_name):
    """List all files (objects) in a folder (bucket) in the mock S3 service."""
    session = aioboto3.Session()
    async with session.client(
            "s3",
            endpoint_url=mock_s3_url,
            aws_access_key_id="test",
            aws_secret_access_key="test",
            region_name=mock_s3_region,
            use_ssl=False,
    ) as s3:
        objects = await s3.list_objects_v2(Bucket=folder_name)
        return [obj["Key"] for obj in objects.get("Contents", [])]
