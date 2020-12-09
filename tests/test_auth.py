"""Test API auth endpoints."""

from unittest.mock import patch, MagicMock

from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop
from aiounittest import futurized

from metadata_backend.server import init
from metadata_backend.api.auth import AccessHandler
from metadata_backend.conf.conf import aai_config


class AccessHandlerTestCase(AioHTTPTestCase):
    """Api auth class test cases."""

    async def get_application(self):
        """Retrieve web Application for test."""
        return await init()

    '''
    async def setUpAsync(self):
        """Configure mock values for tests."""
        self.session_value = "test_value"
        access_config = {
            "_get_from_session.side_effect": self.fake_access_handler__get_from_session,
        }
        self.patch_access_handler = patch("metadata_backend.api.auth.AccessHandler", **access_config, spec=True)

        self.patch_session_get = patch(
            "metadata_backend.api.auth.AccessHandler._get_from_session",
            return_value=self.session_value,
            autospec=True,
        )
        self.MockedAccessHandler = self.patch_access_handler.start()

    async def tearDownAsync(self):
        """Cleanup mocked stuff."""
        self.patch_access_handler.stop()

    async def fake_access_handler__get_from_session(self, req, key):
        """Fake access handler method for getting a value from session storage."""
        return await futurized(self.session_value)
    '''

    @unittest_run_loop
    async def test_login_with_default_config_values(self):
        """Test that login raises 404 because the AUTH_URL env variable is not a proper endpoint."""
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
    async def test_callback_fails_with_something_else(self):
        """Test that callback endpoint ."""
        self.client.app["Session"] = {"oidc_state": "test_value"}
        response = await self.client.get("/callback?state=test_value&code=code")
        self.assertEqual(response.status, 403)
        resp_json = await response.json()
        self.assertEqual(resp_json["detail"], "Bad user session.")
