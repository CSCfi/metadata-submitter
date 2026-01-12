"""Tests for health API handler."""

import logging
import uuid
from unittest.mock import AsyncMock, patch

from metadata_backend.api.models.health import Health, ServiceHealth

from .common import HandlersTestCase

LOG = logging.getLogger(__name__)
LOG.setLevel(logging.DEBUG)


class HealthAPIHandlerTestCase(HandlersTestCase):
    """Tests for health API handler."""

    async def test_get_health(self):
        """Test health check endpoint."""

        # Test mock response.

        for health_status in [Health.UP, Health.DOWN, Health.ERROR]:

            async def mock_get_handler_health(_, _health_status=health_status):
                return str(uuid.uuid4()), _health_status

            with patch(
                "metadata_backend.api.handlers.health.HealthAPIHandler.get_health",
                new_callable=AsyncMock,
                side_effect=mock_get_handler_health,
            ):
                response = await self.client.get("/health")
                assert response.status == 200
                result = await response.json()
                health = ServiceHealth.model_validate(result)
                assert health.status == health_status
                for status in health.services.values():
                    assert status == health_status

        # Test real response.

        response = await self.client.get("/health")
        assert response.status == 200
        result = await response.json()
        health = ServiceHealth.model_validate(result)
        # The database must be UP during unit tests.
        assert health.services["database"] == Health.UP
