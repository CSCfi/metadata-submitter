"""Tests for key API handler."""

import uuid

from starlette import status

from metadata_backend.api.services.auth import ApiKey
from metadata_backend.conf.conf import API_PREFIX
from tests.unit.patches.user import patch_verify_authorization, patch_verify_user_project


async def test_create_get_delete_api_key(csc_client) -> None:
    """Test API key creation, listing and revoking."""
    with (
        patch_verify_authorization,
        patch_verify_user_project,
    ):
        key_id_1 = str(uuid.uuid4())
        key_id_2 = str(uuid.uuid4())

        # Create first key.
        response = csc_client.post(f"{API_PREFIX}/api/keys", json=ApiKey(key_id=key_id_1).model_dump(mode="json"))
        assert response.status_code == 200

        # Check first key exists.
        response = csc_client.get(f"{API_PREFIX}/api/keys")
        assert response.status_code == status.HTTP_200_OK
        json = response.json()
        assert key_id_1 in [ApiKey(**key).key_id for key in json]

        # Create second key.
        response = csc_client.post(f"{API_PREFIX}/api/keys", json=ApiKey(key_id=key_id_2).model_dump(mode="json"))
        assert response.status_code == status.HTTP_200_OK

        # Check first and second key exist.
        response = csc_client.get(f"{API_PREFIX}/api/keys")
        assert response.status_code == status.HTTP_200_OK
        json = response.json()
        assert key_id_1 in [ApiKey(**key).key_id for key in json]
        assert key_id_2 in [ApiKey(**key).key_id for key in json]

        # Remove second key.
        response = csc_client.request(
            method="DELETE", url=f"{API_PREFIX}/api/keys", json=ApiKey(key_id=key_id_2).model_dump(mode="json")
        )
        assert response.status_code == status.HTTP_204_NO_CONTENT

        # Check first key exists.
        response = csc_client.get(f"{API_PREFIX}/api/keys")
        assert response.status_code == status.HTTP_200_OK
        json = response.json()
        assert key_id_1 in [ApiKey(**key).key_id for key in json]
        assert key_id_2 not in [ApiKey(**key).key_id for key in json]
