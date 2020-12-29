"""Test health check endpoint."""

from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop

from metadata_backend.server import init


class HealthTestCase(AioHTTPTestCase):
    """Health endpoint test cases."""

    async def get_application(self):
        """Retrieve web Application for test."""
        server = await init()
        return server

    @unittest_run_loop
    async def test_health_check_is_down(self):
        """Test that the health check returns a partially down status because a mongo db is not connected."""
        response = await self.client.get("/health")
        self.assertEqual(response.status, 200)
        self.assertEqual(response.content_type, "application/json")
        health_json = {"status": "Partially down", "services": {"database": {"status": "Down"}}}
        self.assertEqual(health_json, await response.json())
