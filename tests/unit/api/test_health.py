"""Test health check endpoint."""

from aiohttp.test_utils import AioHTTPTestCase

from metadata_backend.server import init


class HealthTestCase(AioHTTPTestCase):
    """Health endpoint test cases."""

    async def get_application(self):
        """Retrieve web Application for test."""
        server = await init()
        return server

    async def setUpAsync(self):
        """Configure values and patches for testing."""
        self.health_status = {
            "services": {
                "datacite": {"status": "Error"},
                "pid": {"status": "Error"},
                "metax": {"status": "Down"},
                "rems": {"status": "Down"},
                "aai": {"status": "Error"},
                "admin": {"status": "Down"},
                "keystone": {"status": "Down"},
            },
            "status": "Partially down",
        }

        self.app = await self.get_application()
        self.server = await self.get_server(self.app)
        self.client = await self.get_client(self.server)

        await self.client.start_server()

    async def tearDownAsync(self):
        """Cleanup mocked stuff."""
        await self.client.close()

    async def test_health_check_is_down(self):
        """Test that the health check returns down status for all services."""
        response = await self.client.get("/health")
        self.assertEqual(response.status, 200)
        self.assertEqual(response.content_type, "application/json")
        self.assertEqual(self.health_status, await response.json())
