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
from typing import Any

import ujson

API_PREFIX = "/v1"

# 1) Set frontend folder to be inside metadata_backend modules root
frontend_static_files = Path(__file__).parent.parent / "frontend"

# 2.1) Path to swagger HTML file
swagger_static_path = Path(__file__).parent.parent / "swagger" / "index.html"

DEPLOYMENT_CSC = "CSC"
DEPLOYMENT_NBIS = "NBIS"

# TODO(improve): read all env variables using BaseSettings

file_names = [
    "languages.json",
    "fields_of_science.json",
    "geo_locations.json",
    "ror_organizations.json",
]

METAX_REFERENCE_ROOT = Path(__file__).parent.parent / "conf" / "metax_references"
METAX_REFERENCE_DATA: dict[str, dict[Any, Any]] = {
    "languages": {},
    "fields_of_science": {},
    "geo_locations": {},
    "ror_organizations": {},
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


POLLING_INTERVAL = int(os.getenv("POLLING_INTERVAL", "3600"))
