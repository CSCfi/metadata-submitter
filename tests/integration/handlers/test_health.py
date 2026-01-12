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

            # Check overall service health.

            services = health.services.values()

            if Health.ERROR in services:
                assert health.status == Health.ERROR
            elif Health.DOWN in services:
                assert health.status == Health.DOWN
            else:
                assert health.status == Health.UP

            # Check individual service health.

            # The services must be UP during integration tests.
            assert health.services["datacite"] == Health.UP
            assert health.services["pid"] == Health.UP
            assert health.services["metax"] == Health.UP
            assert health.services["rems"] == Health.UP
            assert health.services["auth"] == Health.UP
            assert health.services["keystone"] == Health.UP
            assert health.services["database"] == Health.UP
