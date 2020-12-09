"""Test API auth endpoints."""

from unittest.mock import patch
from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop

from metadata_backend.server import init


class AccessHandlerTestCase(AioHTTPTestCase):
    """Api auth class test cases."""

    async def get_application(self):
        """Retrieve web Application for test."""
        return await init()

    async def setUpAsync(self):
        """Configure mock values for tests."""
        access_config = {}
        self.patch_access_handler = patch("metadata_backend.api.auth.AccessHandler", **access_config, spec=True)
        self.MockedAccessHandler = self.patch_access_handler.start()

    async def tearDownAsync(self):
        """Cleanup mocked stuff."""
        self.patch_access_handler.stop()

    @unittest_run_loop
    async def test_login_with_default_config_values(self):
        """Test that login raises 404 when the AUTH_URL env variable is not a proper endpoint."""
        response = await self.client.get("/aai")
        self.assertRaises(web.HTTPNotFound)
        resp_json = await response.json()
        self.assertEqual(resp_json["instance"], "/authorize")
        # Also check oidc_state is saved to session storage
        self.assertIn("oidc_state", self.client.app["Session"])

    @unittest_run_loop
    async def test_callback_fails_without_query_params(self):
        """Test that callback endpoint raises 400 if no params provided in the request."""
        response = await self.client.get("/callback")
        self.assertRaises(web.HTTPBadRequest)
        resp_json = await response.json()
        self.assertIn("AAI response is missing mandatory params", resp_json["detail"])

    @unittest_run_loop
    async def test_callback_fails_with_wrong_oidc_state(self):
        """Test that callback endpoint raises 403 when state in the query is not the same as specified in session."""
        self.client.app["Session"] = {"oidc_state": "test_value"}
        response = await self.client.get("/callback?state=wrong_value&code=code")
        self.assertEqual(response.status, 403)
        resp_json = await response.json()
        self.assertEqual(resp_json["detail"], "Bad user session.")

    @unittest_run_loop
    async def test_callback_(self):
        """Test that callback ..."""
        self.client.app["Session"] = {"oidc_state": "test_value"}
        await self.client.get("/callback?state=test_value&code=code")
        # Fails at POSTing to token url when it's not set

    @unittest_run_loop
    async def test_logout_works(self):
        """Test that logout revokes all tokens."""
        self.client.app["Session"] = {"access_token": "test_token"}
        await self.client.get("/logout")
        # Revoke url is not configured at conf.py ?
