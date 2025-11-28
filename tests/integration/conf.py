"""Constants and variables used in integration tests."""

import logging
import os
from pathlib import Path

import aiohttp

FORMAT = "[%(asctime)s][%(name)s][%(process)d %(processName)s][%(levelname)-8s](L:%(lineno)s) %(funcName)s: %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
logging.basicConfig(format=FORMAT, datefmt=DATE_FORMAT)


testfiles_root = Path(__file__).parent.parent / "test_files"
test_fega_xml_files = [
    ("study", "SRP000539.xml"),
    ("sample", "SRS001433.xml"),
    ("run", "ERR000076.xml"),
    ("experiment", "ERX000119.xml"),
    ("experiment", "paired.xml"),
    ("experiment", "sample_description.xml"),
    ("analysis", "ERZ266973.xml"),
    ("analysis", "processed_reads_analysis.xml"),
    ("analysis", "assembly_graph_analysis.xml"),
    ("analysis", "reference_alignment_analysis.xml"),
    ("analysis", "reference_sequence_analysis.xml"),
    ("analysis", "sequence_assembly_analysis.xml"),
    ("analysis", "sequence_variation_analysis.xml"),
    ("dac", "dac.xml"),
    ("policy", "policy.xml"),
    ("dataset", "dataset.xml"),
]
test_bigpicture_xml_files = [
    ("bpimage", "images_single.xml"),
    ("bpdataset", "dataset.xml"),
    ("bpobservation", "observation.xml"),
    ("bpannotation", "annotation.xml"),
]
test_fega_json_files = [
    ("study", "SRP000539.json", "SRP000539.json"),
    ("sample", "SRS001433.json", "SRS001433.json"),
    ("dataset", "dataset.json", "dataset.json"),
    ("run", "ERR000076.json", "ERR000076.json"),
    ("experiment", "ERX000119.json", "ERX000119.json"),
    ("analysis", "ERZ266973.json", "ERZ266973.json"),
]

API_PREFIX = "/v1"
base_url = os.getenv("BASE_URL", "http://localhost:5430")
mock_auth_url = os.getenv("OIDC_URL_TEST", "http://localhost:8000")
objects_url = f"{base_url}{API_PREFIX}/objects"
submissions_url = f"{base_url}{API_PREFIX}/submissions"
publish_url = f"{base_url}{API_PREFIX}/publish"
announce_url = f"{base_url}{API_PREFIX}/announce"
schemas_url = f"{base_url}{API_PREFIX}/schemas"
workflows_url = f"{base_url}{API_PREFIX}/workflows"
files_url = f"{base_url}{API_PREFIX}/buckets"
metax_url = f"{os.getenv("METAX_URL", "http://localhost:8002")}"
metax_api = f"{metax_url}/rest/v2/datasets"
datacite_url = f"{os.getenv("DATACITE_API", "http://localhost:8001")}"
datacite_prefix = f"{os.getenv("DATACITE_PREFIX", "10.xxxx")}"
mock_pid_prefix = "10.80869"
taxonomy_url = f"{base_url}{API_PREFIX}/taxonomy"
admin_url = f"{os.getenv("ADMIN_URL", "http://localhost:8004")}"
auth = aiohttp.BasicAuth(os.getenv("METAX_USER", "sd"), os.getenv("METAX_PASS", "test"))
mock_s3_url = f"{os.getenv("S3_ENDPOINT", "http://localhost:8006")}"
mock_s3_region = f"{os.getenv("S3_REGION", "us-east-1")}"

user_id = "current"
test_user_given = "Given"
test_user_family = "Family"
test_user = "user_given@test.what"

other_test_user_given = "Mock"
other_test_user_family = "Family"
other_test_user = "mock_user@test.what"

admin_test_user_given = "Admin Mock"
admin_test_user_family = "Admin Family"
admin_test_user = "admin_user@test.what"
