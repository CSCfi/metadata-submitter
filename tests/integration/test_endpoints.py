"""Test other endpoints."""
import logging

from tests.integration.conf import base_url, schemas_url, test_schemas, workflows_url

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
            assert res["services"]["database"]["status"] == "Ok"


class TestOtherApiEndpoints:
    """Test other api endpoints."""

    async def test_schemas_endpoint(self, client_logged_in):
        """Test that schemas' endpoint return 200."""
        for schema, expected_status in test_schemas:
            async with client_logged_in.get(f"{schemas_url}/{schema}") as resp:
                assert resp.status == expected_status, f"{resp.status} {schema}"

    async def test_workflows_endpoint(self, client_logged_in):
        """Test that schemas' endpoint return 200."""
        async with client_logged_in.get(f"{workflows_url}") as resp:
            assert resp.status == 200, resp.status
            workflows = await resp.json()

        for workflow_name in workflows.keys():
            async with client_logged_in.get(f"{workflows_url}/{workflow_name}") as resp:
                assert resp.status == 200, resp.status
                workflow = await resp.json()
                assert workflow_name == workflow["name"]
