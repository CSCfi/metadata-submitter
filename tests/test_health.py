"""Test health check endpoint."""

from unittest.mock import patch

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
        self.health_status = {"services": {"database": {"status": "Ok"}}, "status": "Ok"}

        class_motorclient = "metadata_backend.api.health.AsyncIOMotorClient"
        motorclient_config = {"server_info.side_effect": self.fake_asynciomotorclient_server_info}
        self.patch_motorclient = patch(class_motorclient, **motorclient_config, spec=True)
        self.MockedMotorClient = self.patch_motorclient.start()

        self.app = await self.get_application()
        self.server = await self.get_server(self.app)
        self.client = await self.get_client(self.server)

        await self.client.start_server()

    async def tearDownAsync(self):
        """Cleanup mocked stuff."""
        self.patch_motorclient.stop()

        await self.client.close()

    async def fake_asynciomotorclient_server_info(self):
        """Fake server info method for a motor client."""
        return True

    async def test_health_check_is_down(self):
        """Test that the health check returns a partially down status because a mongo db is not connected."""
        response = await self.client.get("/health")
        self.assertEqual(response.status, 200)
        self.assertEqual(response.content_type, "application/json")
        self.assertEqual(self.health_status, await response.json())
        self.MockedMotorClient().server_info.assert_called_once()
