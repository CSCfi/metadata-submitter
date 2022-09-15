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
    mongo_db = os.getenv("MONGO_DATABASE", "")
    _base = f"mongodb://{mongo_user}:{mongo_password}@{mongo_host}/{mongo_db}"
    if strtobool(os.getenv("MONGO_SSL", "False")):
        _ca = os.getenv("MONGO_SSL_CA", None)
        # Instead of using ssl_certfile and ssl_keyfile to specify
        # the certificate and private key files respectively, use tlsCertificateKeyFile
        # https://motor.readthedocs.io/en/stable/migrate-to-motor-3.html?highlight=ssl_certfile#renamed-uri-options
        _combined_cert_key = os.getenv("MONGO_SSL_CLIENT_CERT_KEY", None)
        if bool(os.getenv("MONGO_AUTHDB")) and _ca and _combined_cert_key:
            tls = f"?tls=true&tlsCAFile={_ca}&tlsCertificateKeyFile={_combined_cert_key}"
            _authdb = str(os.getenv("MONGO_AUTHDB"))
            auth = f"&authSource={_authdb}"
            mongo_uri = f"{_base}{tls}{auth}"
        else:
            tls = f"?tls=true&tlsCAFile={_ca}&tlsCertificateKeyFile={_combined_cert_key}"
            mongo_uri = f"{_base}{tls}"
    elif bool(os.getenv("MONGO_AUTHDB")):
        _authdb = str(os.getenv("MONGO_AUTHDB"))
        auth = f"?authSource={_authdb}"
        mongo_uri = f"{_base}{auth}"
    else:
        mongo_uri = _base

    if os.getenv("MONGO_DATABASE", "") == "":
        mongo_db = "default"

    return mongo_uri, mongo_db


url, mongo_database = set_conf()


LOG.debug(f"mongodb connection string is {url}")

serverTimeout = 15000
connectTimeout = 15000

API_PREFIX = "/v1"


def create_db_client() -> AsyncIOMotorClient:
    """Initialize database client for AioHTTP App.

    :returns: Coroutine-based Motor client for Mongo operations
    """
    LOG.debug("initialised DB client")
    return AsyncIOMotorClient(url, connectTimeoutMS=connectTimeout, serverSelectionTimeoutMS=serverTimeout)


# 2) Load schema types and descriptions from json
# Default schemas will be ENA schemas
path_to_schema_file = Path(__file__).parent / "schemas.json"
with open(path_to_schema_file, encoding="utf-8") as schema_file:
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

# 4.1) Path to swagger HTML file
swagger_static_path = Path(__file__).parent.parent / "swagger" / "index.html"


# 5) Set up configurations for AAI server
OIDC_ENABLED = False
if "OIDC_URL" in os.environ and bool(os.getenv("OIDC_URL")):
    OIDC_ENABLED = True

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


# 6) Setup integration config

doi_config = {
    "api": os.getenv("DOI_API", "http://localhost:8001/dois"),
    "prefix": os.getenv("DOI_PREFIX", ""),
    "user": os.getenv("DOI_USER", ""),
    "key": os.getenv("DOI_KEY", ""),
    "url": os.getenv("DATACITE_URL", "https://doi.org"),
    "publisher": "CSC - IT Center for Science",
    "discovery_url": os.getenv("DISCOVERY_URL", "https://etsin.fairdata.fi/dataset/"),
}

METAX_ENABLED = os.getenv("METAX_ENABLED", "") == "True"
metax_config = {
    "username": os.getenv("METAX_USER", "sd"),
    "password": os.getenv("METAX_PASS", "test"),
    "url": os.getenv("METAX_URL", "http://mockmetax:8002"),
    "rest_route": "/rest/v2/datasets",
    "publish_route": "/rpc/v2/datasets/publish_dataset",
    "catalog_pid": "urn:nbn:fi:att:data-catalog-sd",
}

file_names = ["identifier_types.json", "languages.json", "fields_of_science.json"]
METAX_REFERENCE_ROOT = Path(__file__).parent.parent / "conf" / "metax_references"
METAX_REFERENCE_DATA: Dict[str, Dict] = {"identifier_types": {}, "languages": {}, "fields_of_science": {}}
# Load metax reference data from different reference files into a single dict used by metax mapper
for ref_file in file_names:
    ref_file_path = METAX_REFERENCE_ROOT / ref_file
    if METAX_ENABLED and not ref_file_path.is_file():
        raise RuntimeError(
            "You must generate the metax references to run submitter: `bash scripts/metax_mappings/fetch_refs.sh`"
        )
    with open(ref_file_path, "r", encoding="utf-8") as file:
        METAX_REFERENCE_DATA[ref_file.replace(".json", "")] = ujson.load(file)

REMS_ENABLED = os.getenv("REMS_ENABLED", "") == "True"
rems_config = {
    "id": os.getenv("REMS_USER_ID", "sd"),
    "key": os.getenv("REMS_KEY", "test"),
    "url": os.getenv("REMS_URL", "http://mockrems:8003"),
}

DATACITE_SCHEMAS = {"study", "dataset", "bpdataset"}
METAX_SCHEMAS = {"study", "dataset"}
