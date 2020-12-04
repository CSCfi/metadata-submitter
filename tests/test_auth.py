"""Test API auth endpoints."""

from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop

from metadata_backend.server import init


class AccessHandlerTestCase(AioHTTPTestCase):
    """Api auth class test cases."""

    async def get_application(self):
        """Retrieve web Application for test."""
        return await init()

    @unittest_run_loop
    async def test_login_with_default_config_values(self):
        """Test that login raises 404 because the AUTH_URL env variable is not a proper endpoint."""
        response = await self.client.get("/aai")
        self.assertRaises(web.HTTPNotFound)
        resp_json = await response.json()
        self.assertEqual(resp_json["instance"], "/authorize")
        # Also check oidc_state is saved to session storage
        self.assertIn("oidc_state", self.client.app["Session"])
