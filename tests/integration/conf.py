"""Constants and variables used in integration tests."""

import os

# Default to localhost for testing outside a container.

auth_url = os.getenv("OIDC_URL", "http://localhost:8000")
base_url = os.getenv("BASE_URL", "http://localhost:5430")
nbis_base_url = os.getenv("NBIS_BASE_URL", "http://localhost:5431")

mock_inbox_url = "http://mockinbox:8006" if os.getenv("CICD") == "true" else "http://localhost:8006"
mock_s3_region = f"{os.getenv('S3_REGION', 'us-east-1')}"
mock_keystone_url = os.getenv("KEYSTONE_ENDPOINT", "http://localhost:5001")

mock_user = "mock_user@test.what"
