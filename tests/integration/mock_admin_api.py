"""Mock aiohttp.web server for Admin API calls."""

import base64
import binascii
import json
import logging
import re
import time
from datetime import datetime
from os import getenv
from typing import List

from aiohttp import ClientSession, client_exceptions, web
from authlib.jose import jwt
from nacl import exceptions as exc
from nacl.public import PublicKey
from pydantic import BaseModel, Field, ValidationError, field_validator

FORMAT = "[%(asctime)s][%(levelname)-8s](L:%(lineno)s) %(funcName)s: %(message)s"
logging.basicConfig(format=FORMAT, datefmt="%Y-%m-%d %H:%M:%S")

LOG = logging.getLogger("server")
LOG.setLevel(getenv("LOG_LEVEL", "INFO"))

mock_auth_url = getenv("OIDC_URL_TEST", "http://localhost:8000")

admins = ["test@test.example"]
files_in_inbox = {
    "test_user": [
        {
            "inboxPath": "/path/to/file.txt",
            "fileStatus": "uploaded",
            "createAt": datetime.now().isoformat(),
        },
        {
            "inboxPath": "/another/test_file.txt",
            "fileStatus": "uploaded",
            "createAt": datetime.now().isoformat(),
        },
        {
            "inboxPath": "/file/in/inbox.txt",
            "fileStatus": "uploaded",
            "createAt": datetime.now().isoformat(),
        },
    ]
}
file_accession_ids = {}
datasets = {}
decryption_key = {}
public_keys = {}


class IngestionModel(BaseModel):
    """Model for validating request json when ingesting file."""

    user: str = Field(min_length=2)
    filepath: str = Field(min_length=2)


class AccessionModel(BaseModel):
    """Model for validating request json when assigning file accession ID."""

    user: str
    filepath: str
    accession_id: str = Field(min_length=2, pattern=r"^\S+$")


class DatasetModel(BaseModel):
    """Model for validating request json when creating dataset."""

    dataset_id: str = Field(min_length=2, pattern=r"^\S+$")
    accession_ids: List[str]

    @field_validator("accession_ids")
    def check_names(cls, accession_ids):
        """Validate the format of each string in 'accession_ids' list."""
        for id in accession_ids:
            if not re.match(r"^\S+$", id):
                raise ValueError(f"Invalid accession ID: {id}")
        return accession_ids


class KeyModel(BaseModel):
    """Model for validating request json when posting a public key."""

    pubkey: str
    description: str


def isAdmin(req: web.Request) -> web.Response | None:
    """Test if subject in jwt is an admin. Assumes jwt is taken from mockauth."""
    auth_header = req.headers.get("Authorization", "")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]

        try:
            claims = jwt.decode(token, decryption_key)
            claims.validate()

            subject = claims.get("sub")
            if subject not in admins:
                LOG.error(f"{subject} is not an admin")
                raise Exception("not authorized")
        except Exception as e:
            return web.json_response({"error": f"access denied: {str(e)}"}, status=401)

        return None

    LOG.error(f"Invalid Authorization header {auth_header}")

    return web.json_response({"error": "bad token"}, status=401)


async def ingest_file(req: web.Request) -> web.Response:
    """Mock endpoint for ingesting file. File status becomes 'verified'."""
    resp = isAdmin(req)
    if resp is not None:
        return resp

    global files_in_inbox
    try:
        content = await req.json()
        ingestion_data = IngestionModel(**content)
    except (json.decoder.JSONDecodeError, ValidationError) as e:
        LOG.exception(f"Invalid JSON payload: {e}")
        return web.json_response(
            {"error": f"json decoding: {e}", "status": 400},
            status=400,
        )

    user_files = files_in_inbox.get(ingestion_data.user, [])
    for file in user_files:
        if ingestion_data.filepath == file.get("inboxPath", ""):
            file["fileStatus"] = "verified"
            LOG.info(f"Ingested file {ingestion_data.filepath}")

            return web.HTTPOk()

    return web.json_response(
        {"error": f"file {ingestion_data.filepath} not found for user {ingestion_data.user}", "status": 400},
        status=400,
    )


async def post_accession_id(req: web.Request) -> web.Response:
    """Mock endpoint for assigning accession ID for file. File must have been ingested."""
    resp = isAdmin(req)
    if resp is not None:
        return resp

    global files_in_inbox
    try:
        content = await req.json()
        accession_data = AccessionModel(**content)
    except (json.decoder.JSONDecodeError, ValidationError) as e:
        LOG.exception(f"Invalid JSON payload: {e}")
        return web.json_response(
            {"error": f"json decoding: {e}", "status": 400},
            status=400,
        )

    if accession_data.accession_id in file_accession_ids:
        reason = f"accession ID {accession_data.accession_id} already in use"
        LOG.error(reason)
        return web.json_response(
            {"error": reason, "status": 400},
            status=400,
        )

    user_files = files_in_inbox.get(accession_data.user, [])
    for file in user_files:
        if accession_data.filepath == file.get("inboxPath", ""):
            if file.get("fileStatus", "") != "verified":
                reason = f"File {accession_data.filepath} is not verified"
                LOG.error(reason)

                return web.json_response(reason=reason, status=400)

            file_accession_ids[accession_data.accession_id] = {
                "user": accession_data.user,
                "filepath": accession_data.filepath,
            }
            file["fileStatus"] = "ready"
            LOG.info(f"Assigned accession ID {accession_data.accession_id} for file {accession_data.filepath}")

            return web.HTTPOk()

    return web.json_response(
        {"error": f"file {accession_data.filepath} not found for user {accession_data.user}", "status": 400},
        status=400,
    )


async def create_dataset(req: web.Request) -> web.Response:
    """Mock endpoint for creating a dataset."""
    resp = isAdmin(req)
    if resp is not None:
        return resp

    try:
        content = await req.json()
        dataset_data = DatasetModel(**content)
    except (json.decoder.JSONDecodeError, ValidationError) as e:
        LOG.exception(f"Invalid JSON payload: {e}")
        return web.json_response(
            {"error": f"json decoding: {e}", "status": 400},
            status=400,
        )

    global file_accession_ids, datasets, files_in_inbox
    found = [id in file_accession_ids.keys() for id in dataset_data.accession_ids]
    if not all(found):
        invalid_ids = [id for (id, f) in zip(dataset_data.accession_ids, found) if not f]
        LOG.error(f"Accession IDs {invalid_ids} not found")
        return web.json_response(
            "accession IDs are not valid",
            status=500,
        )

    datasets[dataset_data.dataset_id] = {"status": "registered", "files": dataset_data.accession_ids}

    for id in dataset_data.accession_ids:
        try:
            user = file_accession_ids[id]["user"]
            path = file_accession_ids[id]["filepath"]
            files_in_inbox[user] = [file for file in files_in_inbox[user] if file["inboxPath"] != path]
            file_accession_ids.pop(id)
        except KeyError as e:
            reason = f"Something went wrong trying to delete files from inbox: {e}"
            LOG.exception(reason)
            raise web.HTTPServerError(reason=reason)

    LOG.info(f"Created dataset {dataset_data.dataset_id}")

    return web.HTTPOk()


async def release_dataset(req: web.Request) -> web.Response:
    """Mock endpoint for releasing a dataset."""
    resp = isAdmin(req)
    if resp is not None:
        return resp

    global datasets
    dataset = req.match_info["dataset"]
    if dataset not in datasets:
        reason = "Dataset not found"
        LOG.error(reason)
        raise web.HTTPNotFound(reason=reason)

    status = datasets[dataset].get("status", "")
    if status == "":
        reason = "Dataset does not have status"
        LOG.error(reason)
        raise web.HTTPBadRequest(reason=reason)

    if status != "registered":
        reason = f"Dataset already {status}"
        LOG.error(reason)
        raise web.HTTPBadRequest(reason=reason)

    LOG.info(f"Released dataset {dataset}")
    datasets[dataset]["status"] = "released"

    return web.HTTPOk()


async def get_user_files(req: web.Request) -> web.Response:
    """Mock endpoint for getting a user's files in inbox."""
    resp = isAdmin(req)
    if resp is not None:
        return resp

    username = req.match_info["username"]
    LOG.debug(username)

    user_files = files_in_inbox.get(username, [])
    return web.json_response(user_files)


async def post_key(req: web.Request) -> web.Response:
    """Mock endpoint for posting a public key."""
    resp = isAdmin(req)
    if resp is not None:
        return resp

    global public_keys
    try:
        content = await req.json()
        key_data = KeyModel(**content)
    except (json.decoder.JSONDecodeError, ValidationError) as e:
        LOG.exception(f"Invalid JSON payload: {e}")
        return web.json_response(
            {"error": f"json decoding: {e}", "status": 400},
            status=400,
        )

    try:
        key_file_content = base64.b64decode(key_data.pubkey).decode("utf-8")
        key64 = (
            key_file_content.replace("-----BEGIN CRYPT4GH PUBLIC KEY-----", "")
            .replace("-----END CRYPT4GH PUBLIC KEY-----", "")
            .strip()
        )
        raw_key = base64.b64decode(key64)
    except binascii.Error as e:
        LOG.exception(f"Invalid JSON payload: {e}")
        return web.json_response(
            {"error": f"base64 decoding: {e}", "status": 400},
            status=400,
        )

    try:
        _ = PublicKey(raw_key)
    except (exc.TypeError, exc.ValueError) as e:
        LOG.exception(f"Invalid JSON payload: {e}")
        return web.json_response(
            {"error": f"not a public key: {e}", "status": 400},
            status=400,
        )

    key_hex = raw_key.hex()
    if key_hex in public_keys:
        LOG.exception("Key hash already exists")
        return web.json_response(
            {"error": "key hash already exists", "status": 409},
            status=409,
        )

    LOG.info(f"Added public key {key_data.pubkey}")
    public_keys[key_hex] = key_data.description

    return web.Response(status=200)


async def init() -> web.Application:
    """Start server."""
    app = web.Application()
    app.router.add_post("/file/ingest", ingest_file)
    app.router.add_post("/file/accession", post_accession_id)
    app.router.add_post("/dataset/create", create_dataset)
    app.router.add_post("/dataset/release/{dataset}", release_dataset)
    app.router.add_get("/users/{username}/files", get_user_files)
    app.router.add_post("/c4gh-keys/add", post_key)

    global decryption_key
    connection_count = 10
    async with ClientSession() as session:
        while connection_count > 0:
            connection_count = connection_count - 1
            try:
                async with session.get(mock_auth_url + "/keyset") as resp:
                    data = await resp.json()
                    decryption_key = data["keys"][0]
            except client_exceptions.ClientConnectorError:
                LOG.warning("Failed to connect to mockauth, trying again")
                time.sleep(2)
                continue
            except (json.decoder.JSONDecodeError, KeyError, IndexError) as e:
                reason = f"Failed to retrieve jwt key: {e}"
                LOG.exception(reason)
                raise web.HTTPServerError(reason=reason)
            else:
                LOG.info("Successfully retrieved decryption key!")
                return app

    reason = "mockauth cannot be reached"
    LOG.error(reason)
    raise web.HTTPServerError(reason=reason)


if __name__ == "__main__":
    web.run_app(init(), port=8004)
