"""Constants and variables used in integration tests."""

import os

from metadata_backend.conf.conf import API_PREFIX

auth_url = os.getenv("OIDC_URL", "http://localhost:8000")

base_url = os.getenv("BASE_URL", "http://localhost:5430")
nbis_base_url = os.getenv("NBIS_BASE_URL", "http://localhost:5431")

objects_url = f"{API_PREFIX}/objects"
submissions_url = f"{API_PREFIX}/submissions"
submit_url = f"{API_PREFIX}/submit"
rems_url = f"{API_PREFIX}/rems"
publish_url = f"{API_PREFIX}/publish"

mock_s3_url = f"{os.getenv('S3_ENDPOINT', 'http://localhost:8006')}"
mock_s3_region = f"{os.getenv('S3_REGION', 'us-east-1')}"
mock_keystone_url = os.getenv("KEYSTONE_ENDPOINT", "http://localhost:5001")

mock_user = "mock_user@test.what"
