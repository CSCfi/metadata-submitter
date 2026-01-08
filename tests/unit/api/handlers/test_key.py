"""Tests for key API handler."""

import uuid

from metadata_backend.api.services.auth import ApiKey
from metadata_backend.conf.conf import API_PREFIX
from metadata_backend.database.postgres.repository import transaction
from tests.unit.conftest import _session_factory

from .common import HandlersTestCase


class KeyAPIHandlerTestCase(HandlersTestCase):
    """Tests for key API handler."""

    async def test_post_get_delete_api_key(self) -> None:
        """Test API key creation, listing and revoking."""
        async with transaction(_session_factory, requires_new=True, rollback_new=True):
            with (
                self.patch_verify_authorization,
                self.patch_verify_user_project,
            ):
                key_id_1 = str(uuid.uuid4())
                key_id_2 = str(uuid.uuid4())

                # Create first key.
                response = await self.client.post(
                    f"{API_PREFIX}/api/keys", json=ApiKey(key_id=key_id_1).model_dump(mode="json")
                )
                self.assertEqual(response.status, 200)

                # Check first key exists.
                response = await self.client.get(f"{API_PREFIX}/api/keys")
                self.assertEqual(response.status, 200)
                json = await response.json()
                assert key_id_1 in [ApiKey(**key).key_id for key in json]

                # Create second key.
                response = await self.client.post(
                    f"{API_PREFIX}/api/keys", json=ApiKey(key_id=key_id_2).model_dump(mode="json")
                )
                self.assertEqual(response.status, 200)

                # Check first and second key exist.
                response = await self.client.get(f"{API_PREFIX}/api/keys")
                self.assertEqual(response.status, 200)
                json = await response.json()
                assert key_id_1 in [ApiKey(**key).key_id for key in json]
                assert key_id_2 in [ApiKey(**key).key_id for key in json]

                # Remove second key.
                response = await self.client.delete(
                    f"{API_PREFIX}/api/keys", json=ApiKey(key_id=key_id_2).model_dump(mode="json")
                )
                self.assertEqual(response.status, 204)

                # Check first key exists.
                response = await self.client.get(f"{API_PREFIX}/api/keys")
                self.assertEqual(response.status, 200)
                json = await response.json()
                assert key_id_1 in [ApiKey(**key).key_id for key in json]
                assert key_id_2 not in [ApiKey(**key).key_id for key in json]
