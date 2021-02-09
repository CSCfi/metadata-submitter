"""Test API auth endpoints."""
from aiohttp.web_exceptions import HTTPForbidden, HTTPUnauthorized, HTTPBadRequest
from metadata_backend.api.auth import AccessHandler
from unittest.mock import MagicMock, patch
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop

from metadata_backend.server import init
from .mockups import Mock_Request, MockResponse, jwt_data, jwk_data, jwt_data_claim_miss, jwt_data_bad_nonce
from aiounittest import AsyncTestCase, futurized
import json
import cryptography.fernet
import hashlib
from os import urandom


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

    async def tearDownAsync(self):
        """Cleanup mocked stuff."""
        self.patch_access_handler.stop()

    @unittest_run_loop
    async def test_login_with_default_config_values(self):
        """Test that login raises 404 when the AUTH_URL env variable is not a proper endpoint."""
        response = await self.client.get("/aai")
        self.assertEqual(response.status, 404)
        resp_json = await response.json()
        self.assertEqual(resp_json["instance"], "/authorize")
        # Also check oidc_state is saved to session storage
        self.assertIn("oidc_state", self.client.app["Session"])

    @unittest_run_loop
    async def test_callback_fails_without_query_params(self):
        """Test that callback endpoint raises 400 if no params provided in the request."""
        response = await self.client.get("/callback")
        self.assertEqual(response.status, 400)
        resp_json = await response.json()
        self.assertEqual("AAI response is missing mandatory params, received: <MultiDictProxy()>", resp_json["detail"])

    @unittest_run_loop
    async def test_callback_fails_with_wrong_oidc_state(self):
        """Test that callback endpoint raises 403 when state in the query is not the same as specified in session."""
        self.client.app["Session"] = {"oidc_state": "mock_oidc_state_value"}
        response = await self.client.get("/callback?state=wrong_value&code=code")
        self.assertEqual(response.status, 403)
        resp_json = await response.json()
        self.assertEqual(resp_json["detail"], "Bad user session.")

    @unittest_run_loop
    async def test_callback_(self):
        """Test that callback."""
        self.client.app["Session"] = {"oidc_state": "mock_oidc_state_value"}
        response = await self.client.get("/callback?state=mock_oidc_state_value&code=code")
        self.assertEqual(response.status, 500)

    @unittest_run_loop
    async def test_logout_works(self):
        """Test that logout revokes all tokens."""
        self.client.app["Session"] = {"access_token": "mock_token_value"}
        response = await self.client.get("/logout")
        self.assertEqual(response.status, 404)
        self.assertEqual(self.client.app["Session"], {})
        self.assertEqual(self.client.app["Cookies"], set())


class AccessHandlerPassTestCase(AsyncTestCase):
    """API AccessHandler auth class functions."""

    def setUp(self):
        """Configure mock values for tests."""
        access_config = {
            "client_id": "aud2",
            "client_secret": "secret",
            "domain": "http://domain.com:5430",
            "redirect": "http://domain.com:5430",
            "scope": "openid profile email",
            "iss": "http://iss.domain.com:5430",
            "callback_url": "http://domain.com:5430/callback",
            "auth_url": "http://auth.domain.com:5430/authorize",
            "token_url": "http://auth.domain.com:5430/token",
            "user_info": "http://auth.domain.com:5430/userinfo",
            "revoke_url": "http://auth.domain.com:5430/revoke",
            "jwk_server": "http://auth.domain.com:5430/jwk",
            "auth_referer": "http://auth.domain.com:5430",
        }
        self.AccessHandler = AccessHandler(access_config)
        self.AccessHandler.nonce = "nonce"

    def tearDown(self):
        """Cleanup mocked stuff."""
        pass

    async def test_get_key_value_from_session_fail(self):
        """Test retrieving key value pair from session exceptions."""
        request = Mock_Request()
        with self.assertRaises(HTTPUnauthorized):
            await self.AccessHandler._get_from_session(request, "mock_value")

        with self.assertRaises(HTTPForbidden):
            await self.AccessHandler._get_from_session("request", "mock_value")

    async def test_get_jwk_fail(self):
        """Test retrieving JWK exception."""
        with self.assertRaises(HTTPUnauthorized):
            await self.AccessHandler._get_key()

    async def test_jwk_key(self):
        """Test get jwk key."""
        data = {
            "kty": "oct",
            "kid": "018c0ae5-4d9b-471b-bfd6-eef314bc7037",
            "use": "sig",
            "alg": "HS256",
            "k": "hJtXIZ2uSN5kbQfbtTNWbpdmhkV8FJG-Onbc6mxCcYg",
        }
        resp = MockResponse(json.dumps(data), 200)

        with patch("aiohttp.ClientSession.get", return_value=resp):
            result = await self.AccessHandler._get_key()
            self.assertEqual(result, json.dumps(data))

    async def test_set_user_fail(self):
        """Test set user raises exception."""
        request = Mock_Request()
        tk = "something"
        with self.assertRaises(HTTPBadRequest):
            await self.AccessHandler._set_user(request, tk)

    async def test_set_user(self):
        """Test set user success."""
        request = Mock_Request()
        request.app["db_client"] = MagicMock()
        request.app["Session"] = {}
        tk = "something"
        data = {
            "eppn": "eppn@test.fi",
            "given_name": "User",
            "family_name": "Test",
        }
        resp = MockResponse(data, 200)

        with patch("aiohttp.ClientSession.get", return_value=resp):
            with patch("metadata_backend.api.operators.UserOperator.create_user", return_value=futurized("USR12345")):
                await self.AccessHandler._set_user(request, tk)

    async def test_callback_fail(self):
        """Test callback fails."""
        request = Mock_Request()
        request.query["state"] = "state"
        request.query["code"] = "code"
        request.app["Session"] = {"oidc_state": "state"}
        resp_no_token = MockResponse({}, 200)
        resp_400 = MockResponse({}, 400)

        with patch("aiohttp.ClientSession.post", return_value=resp_no_token):
            with self.assertRaises(HTTPBadRequest):
                await self.AccessHandler.callback(request)

        with patch("aiohttp.ClientSession.post", return_value=resp_400):
            with self.assertRaises(HTTPBadRequest):
                await self.AccessHandler.callback(request)

    async def test_callback_pass(self):
        """Test callback correct validation."""
        request = Mock_Request()
        request.query["state"] = "state"
        request.query["code"] = "code"
        request.app["Session"] = {"oidc_state": "state"}
        request.app["Cookies"] = set({})
        request.app["Crypt"] = cryptography.fernet.Fernet(cryptography.fernet.Fernet.generate_key())
        request.app["Salt"] = hashlib.sha256(urandom(512)).hexdigest()

        resp_token = MockResponse(jwt_data, 200)
        resp_jwk = MockResponse(jwk_data, 200)

        with patch("aiohttp.ClientSession.post", return_value=resp_token):
            with patch("aiohttp.ClientSession.get", return_value=resp_jwk):
                with patch("metadata_backend.api.auth.AccessHandler._set_user", return_value=futurized(None)):
                    await self.AccessHandler.callback(request)

    async def test_callback_missing_claim(self):
        """Test callback missing claim validation."""
        request = Mock_Request()
        request.query["state"] = "state"
        request.query["code"] = "code"
        request.app["Session"] = {"oidc_state": "state"}
        request.app["Cookies"] = set({})
        request.app["Crypt"] = cryptography.fernet.Fernet(cryptography.fernet.Fernet.generate_key())
        request.app["Salt"] = hashlib.sha256(urandom(512)).hexdigest()

        resp_token = MockResponse(jwt_data_claim_miss, 200)
        resp_jwk = MockResponse(jwk_data, 200)

        with patch("aiohttp.ClientSession.post", return_value=resp_token):
            with patch("aiohttp.ClientSession.get", return_value=resp_jwk):
                with patch("metadata_backend.api.auth.AccessHandler._set_user", return_value=futurized(None)):
                    with self.assertRaises(HTTPUnauthorized):
                        await self.AccessHandler.callback(request)

    async def test_callback_bad_claim(self):
        """Test callback bad nonce validation."""
        request = Mock_Request()
        request.query["state"] = "state"
        request.query["code"] = "code"
        request.app["Session"] = {"oidc_state": "state"}
        request.app["Cookies"] = set({})
        request.app["Crypt"] = cryptography.fernet.Fernet(cryptography.fernet.Fernet.generate_key())
        request.app["Salt"] = hashlib.sha256(urandom(512)).hexdigest()

        resp_token = MockResponse(jwt_data_bad_nonce, 200)
        resp_jwk = MockResponse(jwk_data, 200)

        with patch("aiohttp.ClientSession.post", return_value=resp_token):
            with patch("aiohttp.ClientSession.get", return_value=resp_jwk):
                with patch("metadata_backend.api.auth.AccessHandler._set_user", return_value=futurized(None)):
                    with self.assertRaises(HTTPForbidden):
                        await self.AccessHandler.callback(request)
