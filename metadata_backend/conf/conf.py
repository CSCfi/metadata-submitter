"""Python-based app configurations.

1) Frontend static files folder
Production version gets frontend SPA from this folder, after it has been built
and inserted here in projects Dockerfile.

2) AAI server
AAI server is needed to authenticate users and get their user ID.

3) External service integration
External services are queried from the application, e.g. Datacite for DOIs.
"""

import os
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urljoin

import ujson
from pydantic import Field, computed_field
from pydantic_settings import BaseSettings

from .taxonomy_files.taxonomy_conf import TAXONOMY_NAME_FILE

API_PREFIX = "/v1"

# 1) Set frontend folder to be inside metadata_backend modules root
frontend_static_files = Path(__file__).parent.parent / "frontend"

# 2.1) Path to swagger HTML file
swagger_static_path = Path(__file__).parent.parent / "swagger" / "index.html"

DEPLOYMENT_CSC = "CSC"
DEPLOYMENT_NBIS = "NBIS"


class DeploymentConfig(BaseSettings):
    """Deployment configuration."""

    DEPLOYMENT: Literal["CSC", "NBIS"] = Field(default="CSC", description="The deployment type.")
    ALLOW_UNSAFE: bool = Field(default=False, description="Allow published submissions to be modifiable.")
    ALLOW_REGISTRATION: bool = Field(
        default=True, description="Allow published submissions to be registered with external services."
    )


deployment_config = DeploymentConfig()


class OIDCConfig(BaseSettings):
    """OIDC configuration."""

    model_config = {"extra": "allow"}  # Allow creation using the constructor.

    BASE_URL: str = Field(description="Application URL")
    OIDC_URL: str = Field(description="OIDC provider URL")
    REDIRECT_URL: str | None = Field(
        default=None,
        description="OIDC redirection URL",
    )
    OIDC_CLIENT_ID: str = Field(
        description="OIDC client ID",
        validation_alias="AAI_CLIENT_ID",  # TODO(improve): rename to OIDC_CLIENT_ID
    )
    OIDC_CLIENT_SECRET: str = Field(
        description="OIDC client secret",
        validation_alias="AAI_CLIENT_SECRET",  # TODO(improve): rename to OIDC_CLIENT_SECRET
    )
    OIDC_SCOPE: str = Field(default="openid profile email", description="OIDC scopes")

    @computed_field
    def redirect_url(self) -> str:
        """Return redirect URL or base URL."""

        return self.REDIRECT_URL or self.BASE_URL

    @computed_field
    def callback_url(self) -> str:
        """Return callback URL based on base URL."""

        return urljoin(self.BASE_URL, "callback")


oidc_config = OIDCConfig()

# TODO(improve): read all env variables using BaseSettings

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

TAXONOMY_NAME_DATA: dict[str, dict[Any, Any]] = {}
# Load taxonomy name data into a single dict
if not TAXONOMY_NAME_FILE.is_file():
    raise RuntimeError(
        "Missing taxonomy file `names.json`. Generate with `bash scripts/taxonomy/generate_name_taxonomy.sh`"
    )

with open(TAXONOMY_NAME_FILE, "r", encoding="utf-8") as file:
    TAXONOMY_NAME_DATA = ujson.load(file)

POLLING_INTERVAL = int(os.getenv("POLLING_INTERVAL", "3600"))
