"""Test health handler."""

import logging

from metadata_backend.api.models.health import Health, ServiceHealth
from tests.integration.conf import base_url

LOG = logging.getLogger(__name__)
LOG.setLevel(logging.DEBUG)


class TestPublicEndpoints:
    """Test health handler."""

    async def test_healthcheck(self, client):
        """Test healthcheck endpoint."""
        async with client.get(f"{base_url}/health") as resp:
            assert resp.status == 200
            result = await resp.json()
            health = ServiceHealth.model_validate(result)

            if any(s == Health.ERROR for s in health.services.values()):
                assert health.status == Health.ERROR
            if any(s == Health.DOWN for s in health.services.values()):
                assert health.status == Health.DOWN
            else:
                assert health.status == Health.UP
