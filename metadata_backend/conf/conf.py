"""Python-based app configurations.

1) Database configurations
You need to specify the necessary environment variables for connecting to
MongoDB.
Currently in use:

- ``MONGO_USERNAME`` - Username for mongodb
- ``MONGO_PASSWORD`` - Password for mongodb
- ``MONGO_HOST`` - MongoDB server hostname, with port specified

Admin access is needed in order to create new databases during runtime.
Default values are the same that are used in docker-compose file
found from root directory.

MongoDB client should be shared across the whole application. Since aiohttp
discourages usage of singletons, recommended way is to initialize database
when setting up server and store db to application instance in server.py
module.

2) Metadata schema types
Schema types (such as ``"submission"``, ``"study"``, ``"sample"``) are needed in
different parts of the application.

3) MongoDB query mappings
Mappings are needed to turn incoming REST api queries into mongodb queries.
Change these if database structure changes.

4) Frontend static files folder
Production version gets frontend SPA from this folder, after it has been built
and inserted here in projects Dockerfile.
"""

import json
import os
from distutils.util import strtobool
from pathlib import Path
from typing import Dict, Tuple

import ujson
from motor.motor_asyncio import AsyncIOMotorClient

from ..helpers.logger import LOG

# 1) Set up database client and custom timeouts for spesific parameters.
# Set custom timeouts and other parameters here so they can be imported to
# other modules if needed.

# If just MONGO_DATABASE is specified it will autenticate the user against it.
# If just MONGO_AUTHDB is specified it will autenticate the user against it.
# If both MONGO_DATABASE and MONGO_AUTHDB are specified,
# the client will attempt to authenticate the specified user to the MONGO_AUTHDB database.
# If both MONGO_DATABASE and MONGO_AUTHDB are unspecified,
# the client will attempt to authenticate the specified user to the admin database.


def set_conf() -> Tuple[str, str]:
    """Set config based on env vars."""
    mongo_user = os.getenv("MONGO_USERNAME", "admin")
    mongo_password = os.getenv("MONGO_PASSWORD", "admin")
    mongo_host = os.getenv("MONGO_HOST", "localhost:27017")
    mongo_database = os.getenv("MONGO_DATABASE", "")
    _base = f"mongodb://{mongo_user}:{mongo_password}@{mongo_host}/{mongo_database}"
    if strtobool(os.getenv("MONGO_SSL", "False")):
        _ca = os.getenv("MONGO_SSL_CA", None)
        _key = os.getenv("MONGO_SSL_CLIENT_KEY", None)
        _cert = os.getenv("MONGO_SSL_CLIENT_CERT", None)
        if bool(os.getenv("MONGO_AUTHDB")) and _ca and _key and _cert:
            tls = f"?tls=true&tlsCAFile={_ca}&ssl_keyfile={_key}&ssl_certfile={_cert}"
            _authdb = str(os.getenv("MONGO_AUTHDB"))
            auth = f"&authSource={_authdb}"
            url = f"{_base}{tls}{auth}"
        else:
            tls = f"?tls=true&tlsCAFile={_ca}&ssl_keyfile={_key}&ssl_certfile={_cert}"
            url = f"{_base}{tls}"
    elif bool(os.getenv("MONGO_AUTHDB")):
        _authdb = str(os.getenv("MONGO_AUTHDB"))
        auth = f"?authSource={_authdb}"
        url = f"{_base}{auth}"
    else:
        url = _base

    if os.getenv("MONGO_DATABASE", "") == "":
        mongo_database = "default"

    return url, mongo_database


url, mongo_database = set_conf()


LOG.debug(f"mongodb connection string is {url}")

serverTimeout = 15000
connectTimeout = 15000


def create_db_client() -> AsyncIOMotorClient:
    """Initialize database client for AioHTTP App.

    :returns: Coroutine-based Motor client for Mongo operations
    """
    LOG.debug("initialised DB client")
    return AsyncIOMotorClient(url, connectTimeoutMS=connectTimeout, serverSelectionTimeoutMS=serverTimeout)


# 2) Load schema types and descriptions from json
# Default schemas will be ENA schemas
path_to_schema_file = Path(__file__).parent / "schemas.json"
with open(path_to_schema_file) as schema_file:
    schema_types = ujson.load(schema_file)


# 3) Define mapping between url query parameters and mongodb queries
query_map = {
    "title": "title",
    "description": "description",
    "centerName": "centerName",
    "name": "name",
    "studyTitle": "descriptor.studyTitle",
    "studyType": "descriptor.studyType",
    "studyAbstract": "descriptor.studyAbstract",
    "studyAttributes": {"base": "studyAttributes", "keys": ["tag", "value"]},
    "sampleName": {"base": "sampleName", "keys": ["taxonId", "scientificName", "commonName"]},
    "scientificName": "sampleName.scientificName",
    "fileType": "files.filetype",
    "studyReference": {"base": "studyRef", "keys": ["accessionId", "refname", "refcenter"]},
    "sampleReference": {"base": "sampleRef", "keys": ["accessionId", "label", "refname", "refcenter"]},
    "experimentReference": {"base": "experimentRef", "keys": ["accessionId", "refname", "refcenter"]},
    "runReference": {"base": "runRef", "keys": ["accessionId", "refname", "refcenter"]},
    "analysisReference": {"base": "analysisRef", "keys": ["accessionId", "refname", "refcenter"]},
}


# 4) Set frontend folder to be inside metadata_backend modules root
frontend_static_files = Path(__file__).parent.parent / "frontend"


# 5) Set up configurations for AAI server

aai_config = {
    "client_id": os.getenv("AAI_CLIENT_ID", "public"),
    "client_secret": os.getenv("AAI_CLIENT_SECRET", "secret"),
    "domain": os.getenv("BASE_URL", "http://localhost:5430"),
    "redirect": f'{os.getenv("REDIRECT_URL")}'
    if bool(os.getenv("REDIRECT_URL"))
    else os.getenv("BASE_URL", "http://localhost:5430"),
    "scope": os.getenv("OIDC_SCOPE", "openid profile email"),
    "callback_url": f'{os.getenv("BASE_URL", "http://localhost:5430").rstrip("/")}/callback',
    "oidc_url": os.getenv("OIDC_URL", ""),
    "auth_method": os.getenv("AUTH_METHOD", "code"),
}


# 6) Set the DataCite REST API values

doi_config = {
    "api": os.getenv("DOI_API", ""),
    "prefix": os.getenv("DOI_PREFIX", ""),
    "user": os.getenv("DOI_USER", ""),
    "key": os.getenv("DOI_KEY", ""),
    "url": os.getenv("DATACITE_URL", "https://doi.org"),
    "publisher": "CSC - IT Center for Science",
    "discovery_url": os.getenv("DISCOVERY_URL", "https://etsin.fairdata.fi/dataset/"),
}

metax_config = {
    "username": os.getenv("METAX_USER", "sd"),
    "password": os.getenv("METAX_PASS", "test"),
    "url": os.getenv("METAX_URL", "http://mockmetax:8002"),
    "rest_route": "/rest/v2/datasets",
    "publish_route": "/rpc/v2/datasets/publish_dataset",
    "catalog_pid": "urn:nbn:fi:att:data-catalog-sd",
}

metax_reference_data: Dict = {"identifier_types": {}}
with open(Path(__file__).parent.parent / "conf/metax_references/identifier_types.json", "r") as codes:
    codes_list = json.load(codes)["codes"]
    for code in codes_list:
        metax_reference_data["identifier_types"][code["codeValue"].lower()] = code["uri"]
