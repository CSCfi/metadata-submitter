"""Constants and variables used in integration tests."""

import os

# Default to localhost for testing outside a container.

auth_url = os.getenv("OIDC_URL", "http://localhost:8005")
base_url = os.getenv("BASE_URL", "http://localhost:5430")
nbis_base_url = os.getenv("NBIS_BASE_URL", "http://localhost:5431")

mock_inbox_url = "http://mockinbox:8006" if os.getenv("CICD") == "true" else "http://localhost:8006"
mock_s3_region = f"{os.getenv('S3_REGION', 'us-east-1')}"
mock_keystone_url = os.getenv("KEYSTONE_ENDPOINT", "http://localhost:5001")

openbao_url = os.getenv("OPENBAO_URL", "http://localhost:8200")
openbao_token = os.getenv("OPENBAO_TOKEN", "test-root-token")
openbao_object_key_name_asymmetric = os.getenv("OPENBAO_OBJECT_KEY_NAME_ASYMMETRIC", "sd-submit-object-key-asymmetric")
openbao_object_key_name_symmetric = os.getenv("OPENBAO_OBJECT_KEY_NAME_SYMMETRIC", "sd-submit-object-key-symmetric")
openbao_kubernetes_role = os.getenv("OPENBAO_KUBERNETES_ROLE", "sd-submit")
openbao_kubernetes_service_account = os.getenv("OPENBAO_KUBERNETES_SERVICE_ACCOUNT", "sd-submit")
openbao_kubernetes_namespace = os.getenv("OPENBAO_KUBERNETES_NAMESPACE", "sd-submit-test")

mock_user = "mock_user@test.what"
