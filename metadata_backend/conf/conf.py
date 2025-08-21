"""Python-based app configurations.

1) Metadata schema types
Schema types (e.g. ``"submission"``, ``"study"``, ``"sample"``) are needed in
different parts of the application.

2) Frontend static files folder
Production version gets frontend SPA from this folder, after it has been built
and inserted here in projects Dockerfile.

3) AAI server
AAI server is needed to authenticate users and get their user ID.

4) External service integration
External services are queried from the application, e.g. Datacite for DOIs.
"""

import os
from pathlib import Path
from typing import Any

import ujson

from ..api.exceptions import NotFoundUserException
from ..helpers.workflow import Workflow
from .taxonomy_files.taxonomy_conf import TAXONOMY_NAME_FILE

API_PREFIX = "/v1"

# 1) Load schema types, descriptions and workflows from json
path_to_schema_file = Path(__file__).parent / "schemas.json"
with open(path_to_schema_file, "rb") as schema_file:
    schema_types = ujson.load(schema_file)

path_to_workflows = Path(__file__).parent / "workflows"
WORKFLOWS: dict[str, Workflow] = {}

for workflow_path in path_to_workflows.iterdir():
    with open(workflow_path, "rb") as workflow_file:
        workflow = ujson.load(workflow_file)
        WORKFLOWS[workflow["name"]] = Workflow(workflow)


def get_workflow(workflow_name: str) -> Workflow:
    """Get workflow definition by name.

    :param workflow_name: Name of the workflow
    :returns: The workflow definition.
    """
    if workflow_name not in WORKFLOWS:
        raise NotFoundUserException(f"Invalid workflow {workflow_name}.")
    return WORKFLOWS[workflow_name]


# 2) Set frontend folder to be inside metadata_backend modules root
frontend_static_files = Path(__file__).parent.parent / "frontend"

# 2.1) Path to swagger HTML file
swagger_static_path = Path(__file__).parent.parent / "swagger" / "index.html"


# 3) Set up configurations for AAI server

aai_config = {
    "client_id": os.getenv("AAI_CLIENT_ID", "public"),
    "client_secret": os.getenv("AAI_CLIENT_SECRET", "secret"),
    "domain": os.getenv("BASE_URL", "http://localhost:5430"),
    "redirect": (
        f'{os.getenv("REDIRECT_URL")}'
        if bool(os.getenv("REDIRECT_URL"))
        else os.getenv("BASE_URL", "http://localhost:5430")
    ),
    "scope": os.getenv("OIDC_SCOPE", "openid profile email"),
    "callback_url": f'{os.getenv("BASE_URL", "http://localhost:5430").rstrip("/")}/callback',
    "oidc_url": os.getenv("OIDC_URL", ""),
    "auth_method": os.getenv("AUTH_METHOD", "code"),
}


# 4) Set up external service integration config

doi_config = {
    "publisher": "CSC - IT Center for Science",
}

# Datacite API currently only for Bigpicture workflow
datacite_config = {
    "api": os.getenv("DATACITE_API", "http://localhost:8001/dois"),
    "prefix": os.getenv("DATACITE_PREFIX", "10.xxxx"),
    "user": os.getenv("DATACITE_USER", ""),
    "key": os.getenv("DATACITE_KEY", ""),
    "url": os.getenv("DATACITE_URL", "https://doi.org"),
}

# CSC PID microservice for other cases
pid_config = {
    "api_url": os.getenv("PID_URL", "http://mockpid:8005"),
    "api_key": os.getenv("PID_APIKEY", ""),
}

metax_config = {
    "username": os.getenv("METAX_USER", "sd"),
    "password": os.getenv("METAX_PASS", "test"),
    "url": os.getenv("METAX_URL", "http://mockmetax:8002"),
    "rest_route": "/rest/v2/datasets",
    "publish_route": "/rpc/v2/datasets/publish_dataset",
    "catalog_pid": "urn:nbn:fi:att:data-catalog-sd",
}

file_names = ["identifier_types.json", "languages.json", "fields_of_science.json", "funding_references.json"]
METAX_REFERENCE_ROOT = Path(__file__).parent.parent / "conf" / "metax_references"
METAX_REFERENCE_DATA: dict[str, dict[Any, Any]] = {
    "identifier_types": {},
    "languages": {},
    "fields_of_science": {},
    "funding_references": {},
}
# Load metax reference data from different reference files into a single dict used by metax mapper
for ref_file in file_names:
    ref_file_path = METAX_REFERENCE_ROOT / ref_file
    if not ref_file_path.is_file():
        raise RuntimeError(
            "You must generate the metax references to run submitter: `bash scripts/metax_mappings/fetch_refs.sh`"
        )
    with open(ref_file_path, "r", encoding="utf-8") as file:
        METAX_REFERENCE_DATA[ref_file.replace(".json", "")] = ujson.load(file)

rems_config = {
    "id": os.getenv("REMS_USER_ID", "sd"),
    "key": os.getenv("REMS_KEY", "test"),
    "url": os.getenv("REMS_URL", "http://mockrems:8003"),
}

admin_config = {
    "url": os.getenv("ADMIN_URL", "http://mockadmin:8004"),
}

BP_REMS_SCHEMA_TYPE = "bprems"  # Metadata object itself is not stored.

BP_SCHEMA_TYPES = [
    "bpannotation",
    "bpdataset",
    "bpimage",
    "bpobservation",
    "bpobserver",
    "bprems",
    "bpsample",
    "bpstaining",
    "bppolicy",
    "bpbiologicalBeing",
    "bpcase",
    "bpspecimen",
    "bpblock",
    "bpslide",
]

TAXONOMY_NAME_DATA: dict[str, dict[Any, Any]] = {}
# Load taxonomy name data into a single dict
if not TAXONOMY_NAME_FILE.is_file():
    raise RuntimeError(
        "Missing taxonomy file `names.json`. Generate with `bash scripts/taxonomy/generate_name_taxonomy.sh`"
    )

with open(TAXONOMY_NAME_FILE, "r", encoding="utf-8") as file:
    TAXONOMY_NAME_DATA = ujson.load(file)

POLLING_INTERVAL = int(os.getenv("POLLING_INTERVAL", "3600"))
