"""Constants and variables used in integration tests."""
import logging
import os
from pathlib import Path

import aiohttp

FORMAT = "[%(asctime)s][%(name)s][%(process)d %(processName)s][%(levelname)-8s](L:%(lineno)s) %(funcName)s: %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
logging.basicConfig(format=FORMAT, datefmt=DATE_FORMAT)

testfiles_root = Path(__file__).parent.parent / "test_files"
test_xml_files = [
    ("study", "SRP000539.xml"),
    ("sample", "SRS001433.xml"),
    ("run", "ERR000076.xml"),
    ("experiment", "ERX000119.xml"),
    ("experiment", "paired.xml"),
    ("experiment", "sample_description.xml"),
    ("analysis", "ERZ266973.xml"),
    ("analysis", "processed_reads_analysis.xml"),
    ("analysis", "reference_alignment_analysis.xml"),
    ("analysis", "reference_sequence_analysis.xml"),
    ("analysis", "sequence_assembly_analysis.xml"),
    ("analysis", "sequence_variation_analysis.xml"),
    ("dac", "dac.xml"),
    ("policy", "policy.xml"),
    ("dataset", "dataset.xml"),
    ("image", "images_single.xml"),
    ("bpdataset", "template_dataset.xml"),
]
test_json_files = [
    ("study", "SRP000539.json", "SRP000539.json"),
    ("sample", "SRS001433.json", "SRS001433.json"),
    ("dataset", "dataset.json", "dataset.json"),
    ("run", "ERR000076.json", "ERR000076.json"),
    ("experiment", "ERX000119.json", "ERX000119.json"),
    ("analysis", "ERZ266973.json", "ERZ266973.json"),
]
test_schemas = [
    ("submission", 200),
    ("study", 200),
    # ("project", 200),
    ("sample", 200),
    ("experiment", 200),
    ("run", 200),
    ("dac", 200),
    ("policy", 200),
    ("dataset", 200),
    ("datacite", 200),
    ("image", 200),
    ("bpdataset", 200),
    ("bpsample", 200),
]
API_PREFIX = "/v1"
base_url = os.getenv("BASE_URL", "http://localhost:5430")
mock_auth_url = os.getenv("OIDC_URL_TEST", "http://localhost:8000")
objects_url = f"{base_url}{API_PREFIX}/objects"
drafts_url = f"{base_url}{API_PREFIX}/drafts"
templates_url = f"{base_url}{API_PREFIX}/templates"
submissions_url = f"{base_url}{API_PREFIX}/submissions"
users_url = f"{base_url}{API_PREFIX}/users"
submit_url = f"{base_url}{API_PREFIX}/submit"
publish_url = f"{base_url}{API_PREFIX}/publish"
schemas_url = f"{base_url}{API_PREFIX}/schemas"
metax_url = f"{os.getenv('METAX_URL', 'http://localhost:8002')}/rest/v2/datasets"
datacite_url = f"{os.getenv('DOI_API', 'http://localhost:8001/dois')}"
auth = aiohttp.BasicAuth(os.getenv("METAX_USER", "sd"), os.getenv("METAX_PASS", "test"))
# to form direct contact to db with eg create_submission()
DATABASE = os.getenv("MONGO_DATABASE", "default")
AUTHDB = os.getenv("MONGO_AUTHDB", "admin")
HOST = os.getenv("MONGO_HOST", "localhost:27017")
TLS = os.getenv("MONGO_SSL", False)

user_id = "current"
test_user_given = "Given"
test_user_family = "Family"
test_user = "user_given@test.what"

other_test_user_given = "Mock"
other_test_user_family = "Family"
other_test_user = "mock_user@test.what"
