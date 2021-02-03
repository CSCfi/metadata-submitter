"""Python-based app configurations.

1) Database configurations
You need to specify the necessary environment variables for connecting to
MongoDB.
Currently in use:

- ``MONGO_INITDB_ROOT_USERNAME`` - Admin username for mongodb
- ``MONGO_INITDB_ROOT_PASSWORD`` - Admin password for mongodb
- ``MONGODB_HOST`` - Mongodb server hostname, with port specified

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

3) Mongodb query mappings
Mappings are needed to turn incoming REST api queries into mongodb queries.
Change these if database structure changes.

4) Frontend static files folder
Production version gets frontend SPA from this folder, after it has been built
and inserted here in projects Dockerfile.
"""

import json
import os
from pathlib import Path

from motor.motor_asyncio import AsyncIOMotorClient

from ..helpers.logger import LOG

# 1) Set up database client and custom timeouts for spesific parameters.
# Set custom timeouts and other parameters here so they can be imported to
# other modules if needed.

mongo_user = os.getenv("MONGO_INITDB_ROOT_USERNAME", "admin")
mongo_password = os.getenv("MONGO_INITDB_ROOT_PASSWORD", "admin")
mongo_host = os.getenv("MONGODB_HOST", "localhost:27017")
mongo_authdb = os.getenv("MONGODB_AUTHDB", "")
_base = f"mongodb://{mongo_user}:{mongo_password}@{mongo_host}/{mongo_authdb}"
if bool(os.getenv("MONGO_SSL", None)):
    _ca = os.getenv("MONGO_SSL_CA", None)
    _cert_key = os.getenv("MONGO_SSL_CLIENT_KEY", None)

    tls = f"?tls=true&tlsCAFile={_ca}&tlsCertificateKeyFile={_cert_key}"
    url = f"{_base}{tls}"
else:
    url = _base

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
path_to_schema_file = Path(__file__).parent / "ena_schemas.json"
with open(path_to_schema_file) as schema_file:
    schema_types = json.load(schema_file)


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
    "scope": "openid profile email",
    "iss": os.getenv("ISS_URL", ""),
    "callback_url": f'{os.getenv("BASE_URL", "http://localhost:5430").rstrip("/")}/callback',
    "auth_url": f'{os.getenv("AUTH_URL", "")}'
    if bool(os.getenv("AUTH_URL"))
    else f'{os.getenv("OIDC_URL", "").rstrip("/")}/authorize',
    "token_url": f'{os.getenv("OIDC_URL", "").rstrip("/")}/token',
    "user_info": f'{os.getenv("OIDC_URL", "").rstrip("/")}/userinfo',
    "revoke_url": f'{os.getenv("OIDC_URL", "").rstrip("/")}/revoke',
    "jwk_server": f'{os.getenv("JWK_URL", "")}',
    "auth_referer": f'{os.getenv("AUTH_REFERER", "")}',
}
