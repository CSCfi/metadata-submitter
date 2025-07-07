"""Test API middlewares."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

from aiohttp import FormData
from aiohttp.test_utils import AioHTTPTestCase

from metadata_backend.conf.conf import API_PREFIX
from metadata_backend.server import init


class ErrorMiddlewareTestCase(AioHTTPTestCase):
    """Error handling middleware test cases."""

    async def get_application(self):
        """Retrieve web Application for test."""
        return await init()

    async def setUpAsync(self):
        """Configure default values for testing and other modules.

        This patches used modules and sets default return values for their
        methods. Also sets up reusable test variables for different test
        methods.
        """
        self.app = await self.get_application()
        self.server = await self.get_server(self.app)
        self.client = await self.get_client(self.server)

        self.patch_verify_authorization = patch(
            "metadata_backend.api.middlewares.verify_authorization",
            new=AsyncMock(return_value=("mock-userid", "mock-username")),
        )

        await self.client.start_server()

    async def test_bad_request_returns_json_response(self):
        """Test that the middleware returns bad requests (400) in JSON with problem details."""
        with self.patch_verify_authorization:
            response = await self.client.post(f"{API_PREFIX}/objects/dataset", json={})
            self.assertEqual(response.status, 400)
            self.assertEqual(response.content_type, "application/problem+json")
            resp_dict = await response.json()
            self.assertEqual("Bad Request", resp_dict["title"])
            self.assertIn("Submission ID is a required query parameter.", resp_dict["detail"])
            self.assertEqual(f"{API_PREFIX}/objects/dataset", resp_dict["instance"])

    async def test_bad_url_returns_json_response(self):
        """Test that the middleware returns bad URL requests as not found (404) in JSON with problem details."""
        with self.patch_verify_authorization:
            response = await self.client.get(f"{API_PREFIX}/bad_url")
            self.assertEqual(response.status, 404)
            self.assertEqual(response.content_type, "application/problem+json")
            resp_dict = await response.json()
            self.assertEqual("Not Found", resp_dict["title"])
