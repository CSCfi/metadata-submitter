"""Test API auth endpoints."""
from aiohttp.web_exceptions import HTTPForbidden, HTTPInternalServerError, HTTPSeeOther, HTTPBadRequest
from metadata_backend.api.auth import AccessHandler
from unittest.mock import MagicMock, patch
from aiohttp.test_utils import AioHTTPTestCase
from metadata_backend.api.middlewares import generate_cookie

from metadata_backend.server import init
from .mockups import (
    get_request_with_fernet,
)
from unittest import IsolatedAsyncioTestCase


class AccessHandlerFailTestCase(AioHTTPTestCase):
    """API AccessHandler auth fails class test cases."""

    async def get_application(self):
        """Retrieve web Application for test."""
        return await init()

    async def setUpAsync(self):
        """Configure mock values for tests."""
        access_config = {}
        self.patch_access_handler = patch("metadata_backend.api.auth.AccessHandler", **access_config, spec=True)
        self.MockedAccessHandler = self.patch_access_handler.start()
        self.app = await self.get_application()
        self.server = await self.get_server(self.app)
        self.client = await self.get_client(self.server)

        await self.client.start_server()

    async def tearDownAsync(self):
        """Cleanup mocked stuff."""
        self.patch_access_handler.stop()
        await self.client.close()

    async def test_login_with_default_config_values(self):
        """Test that login raises 500 when OIDC is improperly configured."""
        with patch("oidcrp.rp_handler.RPHandler.begin", side_effect=Exception):
            response = await self.client.get("/aai")
            self.assertEqual(response.status, 500)
            resp_json = await response.json()
            self.assertEqual("OIDC authorization request failed.", resp_json["detail"])

    async def test_callback_fails_without_query_params(self):
        """Test that callback endpoint raises 400 if no params provided in the request."""
        response = await self.client.get("/callback")
        self.assertEqual(response.status, 400)
        resp_json = await response.json()
        self.assertEqual("AAI response is missing mandatory params, received: <MultiDictProxy()>", resp_json["detail"])

    async def test_callback_fails_with_wrong_oidc_state(self):
        """Test that callback endpoint raises 403 when state in the query is not the same as specified in session."""
        with patch("oidcrp.rp_handler.RPHandler.get_session_information", side_effect=KeyError):
            response = await self.client.get("/callback?state=wrong_value&code=code")
            self.assertEqual(response.status, 403)
            resp_json = await response.json()
            self.assertEqual(resp_json["detail"], "Bad user session.")

    async def test_logout_works(self):
        """Test that logout revokes all tokens."""
        request = get_request_with_fernet()
        request.app["Crypt"] = self.client.app["Crypt"]
        cookie, cookiestring = generate_cookie(request)
        self.client.app["Session"] = {cookie["id"]: {"access_token": "mock_token_value"}}
        response = await self.client.get("/logout", cookies={"MTD_SESSION": cookiestring})
        self.assertEqual(response.status, 404)
        self.assertEqual(self.client.app["Session"], {})
        self.assertEqual(self.client.app["Cookies"], set())


class AccessHandlerPassTestCase(IsolatedAsyncioTestCase):
    """API AccessHandler auth class functions."""

    def setUp(self):
        """Configure mock values for tests."""
        access_config = {
            "client_id": "aud2",
            "client_secret": "secret",
            "domain": "http://domain.com:5430",
            "redirect": "http://domain.com:5430",
            "scope": "openid profile email",
            "callback_url": "http://domain.com:5430/callback",
            "oidc_url": "http://auth.domain.com:5430",
            "auth_method": "code",
        }
        self.AccessHandler = AccessHandler(access_config)

    def tearDown(self):
        """Cleanup mocked stuff."""
        pass

    async def test_set_user(self):
        """Test set user success."""
        request = get_request_with_fernet()
        session_id = "session_id"
        new_user_id = "USR12345"

        request.app["db_client"] = MagicMock()
        request.app["Session"] = {session_id: {}}
        user_data = {
            "eppn": "eppn@test.fi",
            "given_name": "User",
            "family_name": "Test",
        }

        with patch("metadata_backend.api.operators.UserOperator.create_user", return_value=new_user_id):
            await self.AccessHandler._set_user(request, session_id, user_data)

        self.assertIn("user_info", request.app["Session"][session_id])
        self.assertEqual(new_user_id, request.app["Session"][session_id]["user_info"])

    async def test_login_fail(self):
        """Test login fails due to bad OIDCRP config."""
        # OIDCRP init fails, because AAI config endpoint request fails
        request = get_request_with_fernet()
        with self.assertRaises(HTTPInternalServerError):
            await self.AccessHandler.login(request)

    async def test_login_pass(self):
        """Test login redirects user."""
        response = {"url": "some url"}
        request = get_request_with_fernet()
        with patch("oidcrp.rp_handler.RPHandler.begin", return_value=response):
            with self.assertRaises(HTTPSeeOther):
                await self.AccessHandler.login(request)

    async def test_callback_pass(self):
        """Test callback correct validation."""
        request = get_request_with_fernet()
        request.query["state"] = "state"
        request.query["code"] = "code"

        session = {"iss": "http://auth.domain.com:5430", "auth_request": {}}
        finalize = {"token": "token", "userinfo": {"eppn": "eppn", "given_name": "name", "family_name": "name"}}
        with patch("oidcrp.rp_handler.RPHandler.get_session_information", return_value=session):
            with patch("oidcrp.rp_handler.RPHandler.finalize", return_value=finalize):
                with patch("metadata_backend.api.auth.AccessHandler._set_user", return_value=None):
                    await self.AccessHandler.callback(request)

    async def test_callback_missing_claim(self):
        """Test callback missing claim validation."""
        request = get_request_with_fernet()
        request.query["state"] = "state"
        request.query["code"] = "code"

        session = {"iss": "http://auth.domain.com:5430", "auth_request": {}}
        finalize = {"token": "token", "userinfo": {}}
        with patch("oidcrp.rp_handler.RPHandler.get_session_information", return_value=session):
            with patch("oidcrp.rp_handler.RPHandler.finalize", return_value=finalize):
                with self.assertRaises(HTTPBadRequest):
                    await self.AccessHandler.callback(request)

    async def test_callback_fail_finalize(self):
        """Test callback fail finalize."""
        request = get_request_with_fernet()
        request.query["state"] = "state"
        request.query["code"] = "code"

        session = {"iss": "http://auth.domain.com:5430", "auth_request": {}}
        with patch("oidcrp.rp_handler.RPHandler.get_session_information", return_value=session):
            with self.assertRaises(HTTPBadRequest):
                await self.AccessHandler.callback(request)

    async def test_callback_bad_state(self):
        """Test callback bad state validation."""
        request = get_request_with_fernet()
        request.query["state"] = "state"
        request.query["code"] = "code"

        with self.assertRaises(HTTPForbidden):
            await self.AccessHandler.callback(request)

    async def test_callback_missing_state(self):
        """Test callback bad state validation."""
        request = get_request_with_fernet()
        request.query["code"] = "code"

        with self.assertRaises(HTTPBadRequest):
            await self.AccessHandler.callback(request)

    async def test_callback_missing_code(self):
        """Test callback bad state validation."""
        request = get_request_with_fernet()
        request.query["state"] = "state"

        with self.assertRaises(HTTPBadRequest):
            await self.AccessHandler.callback(request)
