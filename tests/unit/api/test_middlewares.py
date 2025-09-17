"""Test API middlewares."""

from unittest.mock import AsyncMock, patch

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

    async def test_not_found_problem_response(self):
        """Test that the middleware returns not found with problem JSON."""
        with self.patch_verify_authorization:
            # Test submission not found.
            response = await self.client.get(f"{API_PREFIX}/submissions/invalid", json={})
            data = await response.json()
            assert response.status == 404
            assert response.content_type == "application/problem+json"
            assert data["title"] == "Not Found"
            assert data["detail"] == "Submission 'invalid' not found."
            assert data["instance"] == "/v1/submissions/invalid"

            # Test URL not found.
            response = await self.client.get(f"{API_PREFIX}/bad_url")
            data = await response.json()
            assert response.status == 404
            assert response.content_type == "application/problem+json"
            assert data["title"] == "Not Found"

    async def test_bad_request_problem_response(self):
        """Test that the middleware returns bad request with problem JSON."""
        with self.patch_verify_authorization:
            # Test invalid submission.json.
            response = await self.client.post(f"{API_PREFIX}/submissions", json={})
            data = await response.json()
            assert response.status == 400
            assert response.content_type == "application/problem+json"
            assert data["title"] == "Bad Request"
