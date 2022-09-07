"""Test other endpoints."""
import logging

from tests.integration.conf import base_url, schemas_url, test_schemas

LOG = logging.getLogger(__name__)
LOG.setLevel(logging.DEBUG)


class TestHealthEndpoint:
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
            assert res["services"]["database"]["status"] == "Ok"


class TestSchemasEndpoint:
    """Test schemas endpoint."""

    async def test_schemas_endpoint(self, client_logged_in):
        """Test that schemas' endpoint return 200."""
        for schema, expected_status in test_schemas:
            async with client_logged_in.get(f"{schemas_url}/{schema}") as resp:
                assert resp.status == expected_status, f"{resp.status} {schema}"
