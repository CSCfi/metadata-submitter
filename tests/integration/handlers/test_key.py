"""Integration tests for API keys."""

import uuid

import aiohttp

from metadata_backend.conf.deployment import deployment_config
from tests.integration.conf import base_url

KEYS_URL = f"{deployment_config().API_PREFIX_V1}/api/keys"


async def test_api_key_authenticates(sd_client):
    """Test that a request is authenticated with an API key until the key is deleted."""
    key_id = f"key_{uuid.uuid4()}"
    async with sd_client.post(KEYS_URL, json={"key_id": key_id}) as resp:
        api_key = (await resp.text()).strip()

    async with aiohttp.ClientSession(base_url=f"{base_url}/") as client:

        async def get_keys(key: str) -> int:
            async with client.get(KEYS_URL, headers={"Authorization": f"Bearer {key}"}) as resp:
                return resp.status

        assert await get_keys(api_key) == 200
        assert await get_keys(f"{api_key}wrong") == 401

        async with sd_client.delete(KEYS_URL, json={"key_id": key_id}) as resp:
            assert resp.status == 204
        assert await get_keys(api_key) == 401


async def test_create_api_key_duplicate_key_id(sd_client):
    """Test that creating an API key with an existing key id returns 400."""
    key_id = f"key_{uuid.uuid4()}"
    async with sd_client.post(KEYS_URL, json={"key_id": key_id}) as resp:
        assert resp.status == 200

    async with sd_client.post(KEYS_URL, json={"key_id": key_id}) as resp:
        assert resp.status == 400
        assert (await resp.json())["errors"] == ["API key already exists with this key id."]

    async with sd_client.delete(KEYS_URL, json={"key_id": key_id}) as resp:
        assert resp.status == 204
