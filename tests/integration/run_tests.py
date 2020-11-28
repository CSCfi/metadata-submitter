"""
Run integration tests against backend api endpoints.

Deleting from db is currently not supported, objects added to db in different
should be taken into account.
"""

import asyncio
import json
import logging
from pathlib import Path
import xml.etree.ElementTree as ET

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
base_url = "http://localhost:5430"
objects_url = "http://localhost:5430/objects"
drafts_url = "http://localhost:5430/drafts"
folders_url = "http://localhost:5430/folders"
users_url = "http://localhost:5430/users"
submit_url = "http://localhost:5430/submit"
publish_url = "http://localhost:5430/publish"

user_id = "current"
test_user = "test@test.what", "test test"


# === Helper functions ===
async def login(sess):
    """Mock login."""
    async with sess.get(f"{base_url}/aai"):
        LOG.debug("Doing mock user login")


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


async def create_multi_file_request_data(filepairs):
    """Create request data with multiple files.

    :param filepairs: tuple containing pairs of schemas and filenames used for testing
    """
    data = FormData()
    for schema, filename in filepairs:
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
    async with sess.post(f"{objects_url}/{schema}", data=data) as resp:
        LOG.debug(f"Adding new object to {schema}")
        assert resp.status == 201, "HTTP Status code error"
        ans = await resp.json()
        return ans["accessionId"]


async def delete_object(sess, schema, accession_id):
    """Delete metadata object within session."""
    async with sess.delete(f"{objects_url}/{schema}/{accession_id}") as resp:
        LOG.debug(f"Deleting object {accession_id} from {schema}")
        assert resp.status == 204, "HTTP Status code error"


async def post_draft(sess, schema, filename):
    """Post one draft metadata object within session, returns accessionId."""
    data = await create_request_data(schema, filename)
    async with sess.post(f"{drafts_url}/{schema}", data=data) as resp:
        LOG.debug(f"Adding new object to {schema}")
        assert resp.status == 201, "HTTP Status code error"
        ans = await resp.json()
        return ans["accessionId"]


async def get_draft(sess, schema, draft_id):
    """Get and return a drafted metadata object."""
    async with sess.get(f"{drafts_url}/sample/{draft_id}") as resp:
        LOG.debug(f"Checking that {draft_id} JSON exists")
        assert resp.status == 200, "HTTP Status code error"
        ans = await resp.json()
        return json.dumps(ans)


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
    async with sess.post(f"{folders_url}", data=json.dumps(data)) as resp:
        LOG.debug("Adding new folder")
        assert resp.status == 201, "HTTP Status code error"
        ans = await resp.json()
        return ans["folderId"]


async def patch_folder(sess, folder_id, patch):
    """Patch one object folder within session, return folderId."""
    async with sess.patch(f"{folders_url}/{folder_id}", data=json.dumps(patch)) as resp:
        LOG.debug(f"Updating folder {folder_id}")
        assert resp.status == 200, "HTTP Status code error"
        ans_patch = await resp.json()
        assert ans_patch["folderId"] == folder_id, "folder ID error"
        return ans_patch["folderId"]


async def publish_folder(sess, folder_id):
    """Publish one object folder within session, return folderId."""
    async with sess.patch(f"{publish_url}/{folder_id}") as resp:
        LOG.debug(f"Publishing folder {folder_id}")
        assert resp.status == 200, "HTTP Status code error"
        ans = await resp.json()
        assert ans["folderId"] == folder_id, "folder ID error"
        return ans["folderId"]


async def delete_folder(sess, folder_id):
    """Delete object folder within session."""
    async with sess.delete(f"{folders_url}/{folder_id}") as resp:
        LOG.debug(f"Deleting folder {folder_id}")
        assert resp.status == 204, "HTTP Status code error"


async def patch_user(sess, user_id, real_user_id, patch):
    """Patch one user object within session, return userId."""
    async with sess.patch(f"{users_url}/current", data=json.dumps(patch)) as resp:
        LOG.debug(f"Updating user {user_id}")
        assert resp.status == 200, "HTTP Status code error"
        ans_patch = await resp.json()
        assert ans_patch["userId"] == real_user_id, "user ID error"
        return ans_patch["userId"]


async def delete_user(sess, user_id):
    """Delete user object within session."""
    async with sess.delete(f"{users_url}/current") as resp:
        LOG.debug(f"Deleting user {user_id}")
        assert str(resp.url) == "http://localhost:5430/", "redirect url user delete differs"
        assert resp.status == 200, "HTTP Status code error"


# === Integration tests ===
async def test_crud_works(sess, schema, filename):
    """Test REST api POST, GET and DELETE reqs.

    Tries to create new object, gets accession id and checks if correct
    resource is returned with that id. Finally deletes the object and checks it
    was deleted.

    :param schema: name of the schema (folder) used for testing
    :param filename: name of the file used for testing.
    """
    accession_id = await post_object(sess, schema, filename)
    async with sess.get(f"{objects_url}/{schema}/{accession_id}") as resp:
        LOG.debug(f"Checking that {accession_id} JSON is in {schema}")
        assert resp.status == 200, "HTTP Status code error"
    async with sess.get(f"{objects_url}/{schema}/{accession_id}" "?format=xml") as resp:
        LOG.debug(f"Checking that {accession_id} XML is in {schema}")
        assert resp.status == 200, "HTTP Status code error"

    await delete_object(sess, schema, accession_id)
    async with sess.get(f"{objects_url}/{schema}/{accession_id}") as resp:
        LOG.debug(f"Checking that JSON object {accession_id} was deleted")
        assert resp.status == 404, "HTTP Status code error"
    async with sess.get(f"{objects_url}/{schema}/{accession_id}" "?format=xml") as resp:
        LOG.debug(f"Checking that XML object {accession_id} was deleted")
        assert resp.status == 404, "HTTP Status code error"


async def test_crud_drafts_works(sess, schema, filename, filename2):
    """Test drafts REST api POST, PUT and DELETE reqs.

    Tries to create new draft object, gets accession id and checks if correct
    resource is returned with that id. Finally deletes the object and checks it
    was deleted.

    :param schema: name of the schema (folder) used for testing
    :param filename: name of the file used for testing.
    """
    accession_id = await put_draft(sess, schema, filename, filename2)
    async with sess.get(f"{drafts_url}/{schema}/{accession_id}") as resp:
        LOG.debug(f"Checking that {accession_id} JSON is in {schema}")
        assert resp.status == 200, "HTTP Status code error"

    await delete_draft(sess, schema, accession_id)
    async with sess.get(f"{drafts_url}/{schema}/{accession_id}") as resp:
        LOG.debug(f"Checking that JSON object {accession_id} was deleted")
        assert resp.status == 404, "HTTP Status code error"


async def test_patch_drafts_works(sess, schema, filename, filename2):
    """Test REST api POST, PATCH and DELETE reqs.

    Tries to create put and patch object, gets accession id and
    checks if correct resource is returned with that id.
    Finally deletes the object and checks it was deleted.

    :param schema: name of the schema (folder) used for testing
    :param filename: name of the file used for testing.
    """
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


async def test_querying_works(sess):
    """Test query endpoint with working and failing query."""
    accession_ids = await asyncio.gather(*[post_object(sess, schema, filename) for schema, filename in test_xml_files])

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

    await asyncio.gather(
        *[
            delete_object(sess, schema, accession_id)
            for schema, accession_id in list(zip([schema for schema, _ in test_xml_files], accession_ids))
        ]
    )


async def test_getting_all_objects_from_schema_works(sess):
    """Check that /objects/study returns objects with correct pagination."""

    # Add objects
    accession_ids = await asyncio.gather(*[post_object(sess, "study", "SRP000539.xml") for _ in range(13)])

    # Test default values
    async with sess.get(f"{objects_url}/study") as resp:
        assert resp.status == 200
        ans = await resp.json()
        assert ans["page"]["page"] == 1
        assert ans["page"]["size"] == 10
        assert ans["page"]["totalPages"] == 2
        assert ans["page"]["totalObjects"] == 13
        assert len(ans["objects"]) == 10

    # Test with custom pagination values
    async with sess.get(f"{objects_url}/study?page=2&per_page=3") as resp:
        assert resp.status == 200
        ans = await resp.json()
        assert ans["page"]["page"] == 2
        assert ans["page"]["size"] == 3
        assert ans["page"]["totalPages"] == 5
        assert ans["page"]["totalObjects"] == 13
        assert len(ans["objects"]) == 3

    # Test with wrong pagination values
    async with sess.get(f"{objects_url}/study?page=-1") as resp:
        assert resp.status == 400
    async with sess.get(f"{objects_url}/study?per_page=0") as resp:
        assert resp.status == 400

    # Delete objects
    await asyncio.gather(*[delete_object(sess, "study", accession_id) for accession_id in accession_ids])


async def test_crud_folders_works(sess):
    """Test folders REST api POST, GET, PATCH, PUBLISH and DELETE reqs."""
    # Create new folder and check its creation succeeded
    data = {"name": "test", "description": "test folder"}
    folder_id = await post_folder(sess, data)
    async with sess.get(f"{folders_url}/{folder_id}") as resp:
        LOG.debug(f"Checking that folder {folder_id} was created")
        assert resp.status == 200, "HTTP Status code error"

    # Create draft from test XML file and patch the draft into the newly created folder
    draft_id = await post_draft(sess, "sample", "SRS001433.xml")
    patch1 = [{"op": "add", "path": "/drafts", "value": [{"accessionId": draft_id, "schema": "sample"}]}]
    folder_id = await patch_folder(sess, folder_id, patch1)
    async with sess.get(f"{folders_url}/{folder_id}") as resp:
        LOG.debug(f"Checking that folder {folder_id} was patched")
        res = await resp.json()
        assert res["folderId"] == folder_id, "content mismatch"
        assert res["name"] == "test", "content mismatch"
        assert res["description"] == "test folder", "content mismatch"
        assert res["published"] is False, "content mismatch"
        assert res["drafts"] == [{"accessionId": draft_id, "schema": "sample"}], "content mismatch"
        assert res["metadataObjects"] == [], "content mismatch"

    # Get the draft from the collection within this session and post it to objects collection
    draft = await get_draft(sess, "sample", draft_id)
    async with sess.post(f"{objects_url}/sample", data=draft) as resp:
        LOG.debug("Adding draft to actual objects")
        assert resp.status == 201, "HTTP Status code error"
        ans = await resp.json()
        assert ans["accessionId"] != draft_id, "content mismatch"
        accession_id = ans["accessionId"]

    # Patch folder so that original draft becomes an object in the folder
    patch2 = [
        {"op": "add", "path": "/metadataObjects", "value": [{"accessionId": accession_id, "schema": "sample"}]},
    ]
    folder_id = await patch_folder(sess, folder_id, patch2)
    async with sess.get(f"{folders_url}/{folder_id}") as resp:
        LOG.debug(f"Checking that folder {folder_id} was patched")
        res = await resp.json()
        assert res["folderId"] == folder_id, "content mismatch"
        assert res["published"] is False, "content mismatch"
        assert res["drafts"] == [{"accessionId": draft_id, "schema": "sample"}], "content mismatch"
        assert res["metadataObjects"] == [{"accessionId": accession_id, "schema": "sample"}], "content mismatch"

    # Publish the folder
    folder_id = await publish_folder(sess, folder_id)
    async with sess.get(f"{folders_url}/{folder_id}") as resp:
        LOG.debug(f"Checking that folder {folder_id} was patched")
        res = await resp.json()
        assert res["folderId"] == folder_id, "content mismatch"
        assert res["published"] is True, "content mismatch"
        assert res["drafts"] == [], "content mismatch"
        assert res["metadataObjects"] == [{"accessionId": accession_id, "schema": "sample"}], "content mismatch"

    # Delete folder
    await delete_folder(sess, folder_id)
    async with sess.get(f"{folders_url}/{folder_id}") as resp:
        LOG.debug(f"Checking that folder {folder_id} was deleted")
        assert resp.status == 404, "HTTP Status code error"


async def test_crud_users_works(sess):
    """Test users REST api GET, PATCH and DELETE reqs."""
    # Check user exists in database (requires an user object to be mocked)
    async with sess.get(f"{users_url}/{user_id}") as resp:
        LOG.debug(f"Reading user {user_id}")
        assert resp.status == 200, "HTTP Status code error"
        response = await resp.json()
        real_user_id = response["userId"]

    # Add user to session and create a patch to add folder to user
    data = {"name": "test", "description": "test folder"}
    folder_id = await post_folder(sess, data)
    patch = [{"op": "add", "path": "/folders", "value": [folder_id]}]
    await patch_user(sess, user_id, real_user_id, patch)
    async with sess.get(f"{users_url}/{user_id}") as resp:
        LOG.debug(f"Checking that user {user_id} was patched")
        res = await resp.json()
        assert res["userId"] == real_user_id, "content mismatch"
        assert res["name"] == "test test", "content mismatch"
        assert res["drafts"] == [], "content mismatch"
        assert res["folders"] == [folder_id], "content mismatch"

    # Delete user
    await delete_user(sess, user_id)
    # 401 means API is innacessible thus session ended
    # this check is not needed but good to do
    async with sess.get(f"{users_url}/{user_id}") as resp:
        LOG.debug(f"Checking that user {user_id} was deleted")
        assert resp.status == 401, "HTTP Status code error"


async def test_submissions_work(sess):
    """Test actions in submission xml files."""
    # Post original submission with two 'add' actions
    sub_files = [("submission", "ERA521986_valid.xml"), ("study", "SRP000539.xml"), ("sample", "SRS001433.xml")]
    data = await create_multi_file_request_data(sub_files)
    async with sess.post(f"{submit_url}", data=data) as resp:
        LOG.debug("Checking initial submission worked")
        assert resp.status == 200, "HTTP Status code error"
        res = await resp.json()
        assert len(res) == 2, "content mismatch"
        assert res[0]["schema"] == "study", "content mismatch"
        assert res[1]["schema"] == "sample", "content mismatch"
        study_access_id = res[0]["accessionId"]

    # Sanity check that the study object was inserted correctly before modifying it
    async with sess.get(f"{objects_url}/study/{study_access_id}") as resp:
        LOG.debug("Sanity checking that previous object was added correctly")
        assert resp.status == 200, "HTTP Status code error"
        res = await resp.json()
        assert res["accessionId"] == study_access_id, "content mismatch"
        assert res["alias"] == "GSE10966", "content mismatch"
        assert res["descriptor"]["studyTitle"] == (
            "Highly integrated epigenome maps in Arabidopsis - whole genome shotgun bisulfite sequencing"
        ), "content mismatch"

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
    data = await create_multi_file_request_data(sub_files)
    async with sess.post(f"{submit_url}", data=data) as resp:
        LOG.debug("Checking object in initial submission was modified")
        assert resp.status == 200, "HTTP Status code error"
        res = await resp.json()
        assert len(res) == 2, "content mismatch"
        new_study_access_id = res[0]["accessionId"]
        assert study_access_id == new_study_access_id

    # Check the modified object was inserted correctly
    async with sess.get(f"{objects_url}/study/{new_study_access_id}") as resp:
        LOG.debug("Checking that previous object was modified correctly")
        assert resp.status == 200, "HTTP Status code error"
        res = await resp.json()
        assert res["accessionId"] == new_study_access_id, "content mismatch"
        assert res["alias"] == "GSE10966", "content mismatch"
        assert res["descriptor"]["studyTitle"] == ("Different title for testing purposes"), "content mismatch"

    # Remove the accession id that was used for testing from test file
    LOG.debug("Sharing the correct accession ID created in this test instance")
    mod_study = testfiles_root / "study" / "SRP000539_modified.xml"
    tree = ET.parse(mod_study)
    root = tree.getroot()
    for elem in root.iter("STUDY"):
        del elem.attrib["accession"]
    tree.write(mod_study, encoding="utf-8")


async def main():
    """Launch different test tasks and run them."""
    # Test adding and getting objects
    async with aiohttp.ClientSession() as sess:
        await login(sess)
        LOG.debug("=== Testing basic CRUD operations ===")
        await asyncio.gather(*[test_crud_works(sess, schema, file) for schema, file in test_xml_files])

        # Test adding and getting draft objects
        LOG.debug("=== Testing basic CRUD drafts operations ===")
        await asyncio.gather(
            *[test_crud_drafts_works(sess, schema, file, file2) for schema, file, file2 in test_json_files]
        )

        # Test patch and put
        LOG.debug("=== Testing patch and put drafts operations ===")
        await test_crud_drafts_works(sess, "sample", "SRS001433.json", "put.json")
        await test_patch_drafts_works(sess, "study", "SRP000539.json", "patch.json")

        # Test queries
        LOG.debug("=== Testing queries ===")
        await test_querying_works(sess)

        # Test /objects/study endpoint for query pagination
        LOG.debug("=== Testing getting all objects & pagination ===")
        await test_getting_all_objects_from_schema_works(sess)

        # Test creating, reading, updating and deleting folders
        LOG.debug("=== Testing basic CRUD folder operations ===")
        await test_crud_folders_works(sess)

        # Test add, modify, validate and release action with submissions
        LOG.debug("=== Testing actions within submissions ===")
        await test_submissions_work(sess)

        # Test reading, updating and deleting users
        # this needs to be done last as it deletes users
        LOG.debug("=== Testing basic CRUD user operations ===")
        await test_crud_users_works(sess)


if __name__ == "__main__":
    asyncio.run(main())
