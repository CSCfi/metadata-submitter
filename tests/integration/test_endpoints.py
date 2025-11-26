"""Test other endpoints."""

import logging

from tests.integration.conf import base_url

LOG = logging.getLogger(__name__)
LOG.setLevel(logging.DEBUG)


class TestPublicEndpoints:
    """Test health endpoint."""

    async def test_health_check(self, client):
        """Test the health check endpoint.

        :param client: HTTP client in which request call is made
        """
        async with client.get(f"{base_url}/health") as resp:
            LOG.debug("Checking that health status is ok")
            assert resp.status == 200, f"HTTP Status code error, got {resp.status}"
            res = await resp.json()
            assert res["status"] == "Ok"
            assert res["services"]["aai"]["status"] == "Ok"
