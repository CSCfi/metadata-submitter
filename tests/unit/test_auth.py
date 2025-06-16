"""Test API auth endpoints."""

import os
from datetime import timedelta
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, MagicMock, patch

import jwt
from aiohttp.test_utils import AioHTTPTestCase
from aiohttp.web_exceptions import HTTPBadRequest, HTTPInternalServerError, HTTPSeeOther, HTTPUnauthorized

from metadata_backend.api.auth import AccessHandler
from metadata_backend.api.services.auth import (
    API_KEY_ID_LENGTH,
    API_KEY_LENGTH,
    JWT_ALGORITHM,
    JWT_ISSUER,
    JWT_SECRET_ENV,
    AccessService,
)
from metadata_backend.server import init

from .mockups import Mock_Request

# from metadata_backend.api.middlewares import generate_cookie


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

        self.patch_verify_authorization = patch(
            "metadata_backend.api.middlewares.verify_authorization",
            new=AsyncMock(return_value=("mock-userid", "mock-username")),
        )

        await self.client.start_server()

    async def tearDownAsync(self):
        """Cleanup mocked stuff."""
        self.patch_access_handler.stop()
        await self.client.close()

    async def test_login_with_default_config_values(self):
        """Test that login raises 500 when OIDC is improperly configured."""
        with patch("idpyoidc.client.rp_handler.RPHandler.begin", side_effect=Exception):
            response = await self.client.get("/aai")
            self.assertEqual(response.status, 500)
            resp = await response.text()
            self.assertEqual("500: OIDC authorization request failed.", resp)

    async def test_callback_fails_without_query_params(self):
        """Test that callback endpoint raises 401 if no params provided in the request."""
        response = await self.client.get("/callback")
        self.assertEqual(response.status, 401)
        resp = await response.text()
        self.assertEqual("401: AAI response is missing mandatory params, received: <MultiDictProxy()>", resp)

    async def test_callback_fails_with_wrong_oidc_state(self):
        """Test that callback endpoint raises 401 when state in the query is not the same as specified in session."""
        with (
            patch("idpyoidc.client.rp_handler.RPHandler.get_session_information", side_effect=KeyError),
            self.patch_verify_authorization,
        ):
            response = await self.client.get("/callback?state=wrong_value&code=code")
            self.assertEqual(response.status, 401)
            resp = await response.text()
            self.assertEqual(resp, "401: Bad user session.")

    # Logout redirects to frontend, so it only passes if frontend is enabled
    # async def test_logout_works(self):
    #     """Test that logout revokes all tokens."""
    #     with self.p_get_sess:
    #         response = await self.client.get("/logout")
    #         self.assertEqual(response.status, 200)


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

        self.patch_verify_authorization = patch(
            "metadata_backend.api.middlewares.verify_authorization",
            new=AsyncMock(return_value=("mock-userid", "mock-username")),
        )

    async def test_login_fail(self):
        """Test login fails due to bad idpyoidc config."""
        # idpyoidc init fails, because AAI config endpoint request fails
        request = Mock_Request()
        with self.assertRaises(HTTPInternalServerError):
            await self.AccessHandler.login(request)

    async def test_login_pass(self):
        """Test login redirects user."""
        response = "url"
        request = Mock_Request()
        with patch("idpyoidc.client.rp_handler.RPHandler.begin", return_value=response):
            response = await self.AccessHandler.login(request)
            assert isinstance(response, HTTPSeeOther)

    async def test_callback_pass_csc(self):
        """Test callback correct validation (CSC format)."""
        request = Mock_Request()
        request.query["state"] = "state"
        request.query["code"] = "code"

        session = {"iss": "http://auth.domain.com:5430", "code": "code"}
        finalize = {
            "token": "token",
            "userinfo": {"sub": "user", "given_name": "name", "family_name": "name", "sdSubmitProjects": "1000 2000"},
            "state": {},
        }
        db_client = MagicMock()
        db_database = MagicMock()
        db_collection = AsyncMock()
        db_client.__getitem__.return_value = db_database
        db_database.__getitem__.return_value = db_collection

        request.app["db_client"] = db_client

        with patch("idpyoidc.client.rp_handler.RPHandler.get_session_information", return_value=session):
            with patch("idpyoidc.client.rp_handler.RPHandler.finalize", return_value=finalize):
                with patch.dict(os.environ, {JWT_SECRET_ENV: "mock_secret"}):
                    await self.AccessHandler.callback(request)

    async def test_callback_pass_ls(self):
        """Test callback correct validation (LS format)."""
        request = Mock_Request()
        request.query["state"] = "state"
        request.query["code"] = "code"

        session = {"iss": "http://auth.domain.com:5430", "code": "code"}
        finalize = {
            "token": "token",
            "userinfo": {
                "sub": "user",
                "given_name": "name",
                "family_name": "name",
                "eduperson_entitlement": ["group1", "group2"],
            },
            "state": {},
        }
        db_client = MagicMock()
        db_database = MagicMock()
        db_collection = AsyncMock()
        db_client.__getitem__.return_value = db_database
        db_database.__getitem__.return_value = db_collection

        request.app["db_client"] = db_client

        with patch("idpyoidc.client.rp_handler.RPHandler.get_session_information", return_value=session):
            with patch("idpyoidc.client.rp_handler.RPHandler.finalize", return_value=finalize):
                with patch.dict(os.environ, {JWT_SECRET_ENV: "mock_secret"}):
                    await self.AccessHandler.callback(request)

    async def test_callback_missing_claim(self):
        """Test callback missing claim validation."""
        request = Mock_Request()
        request.query["state"] = "state"
        request.query["code"] = "code"

        session = {"iss": "http://auth.domain.com:5430", "auth_request": {}}
        finalize = {
            "token": "token",
            "userinfo": {"given_name": "some", "family_name": "one", "sdSubmitProjects": "1000"},
        }
        with patch("idpyoidc.client.rp_handler.RPHandler.get_session_information", return_value=session):
            with patch("idpyoidc.client.rp_handler.RPHandler.finalize", return_value=finalize):
                with self.assertRaises(HTTPUnauthorized):
                    await self.AccessHandler.callback(request)

    async def test_callback_fail_finalize(self):
        """Test callback fail finalize."""
        request = Mock_Request()
        request.query["state"] = "state"
        request.query["code"] = "code"

        session = {"iss": "http://auth.domain.com:5430", "auth_request": {}}
        with patch("idpyoidc.client.rp_handler.RPHandler.get_session_information", return_value=session):
            with self.assertRaises(HTTPBadRequest):
                await self.AccessHandler.callback(request)

    async def test_callback_bad_state(self):
        """Test callback bad state validation."""
        request = Mock_Request()
        request.query["state"] = "state"
        request.query["code"] = "code"

        with self.assertRaises(HTTPUnauthorized):
            await self.AccessHandler.callback(request)

    async def test_callback_missing_state(self):
        """Test callback bad state validation."""
        request = Mock_Request()
        request.query["code"] = "code"

        with self.assertRaises(HTTPUnauthorized):
            await self.AccessHandler.callback(request)

    async def test_callback_missing_code(self):
        """Test callback bad state validation."""
        request = Mock_Request()
        request.query["state"] = "state"

        with self.assertRaises(HTTPUnauthorized):
            await self.AccessHandler.callback(request)


class AccessServiceTestCase(TestCase):
    """Test Auth API services."""

    def setUp(self) -> None:
        """Configure mock values for tests."""
        self.user_id = "mock-user"
        self.user_name = "mock-user-name"
        self.expiration = timedelta(minutes=10)
        self.jwt_secret = "mock-secret"
        self.env_patcher = patch.dict(os.environ, {JWT_SECRET_ENV: self.jwt_secret})
        self.env_patcher.start()

    def tearDown(self) -> None:
        """Cleanup mocked stuff."""
        self.env_patcher.stop()

    def test_create_jwt_token_contains_required_claims(self) -> None:
        """Test that the JWT token contains the required claims."""
        token = AccessService.create_jwt_token(self.user_id, self.user_name, self.expiration)
        decoded = jwt.decode(token, self.jwt_secret, algorithms=[JWT_ALGORITHM], issuer=JWT_ISSUER)

        self.assertEqual(decoded["sub"], self.user_id)
        self.assertEqual(decoded["user_name"], self.user_name)
        self.assertEqual(decoded["iss"], JWT_ISSUER)
        self.assertIn("exp", decoded)
        self.assertIn("iat", decoded)

    def test_read_jwt_token_returns_user_id(self) -> None:
        """Test that reading a JWT token returns the correct user ID and name."""
        token = AccessService.create_jwt_token(self.user_id, self.user_name, self.expiration)
        user_id, user_name = AccessService.validate_jwt_token(token)
        self.assertEqual(user_id, self.user_id)
        self.assertEqual(user_name, self.user_name)

    def test_create_jwt_token_missing_secret_raises(self) -> None:
        """Test that creating a JWT token raises an error if the secret is not set."""
        os.environ.pop(JWT_SECRET_ENV, None)
        with self.assertRaises(RuntimeError):
            AccessService.create_jwt_token(self.user_id, self.user_name, self.expiration)

    def test_read_jwt_token_missing_secret_raises(self) -> None:
        """Test that reading a JWT token raises an error if the secret is not set."""
        token = AccessService.create_jwt_token(self.user_id, self.user_name, self.expiration)
        os.environ.pop(JWT_SECRET_ENV, None)
        with self.assertRaises(RuntimeError):
            AccessService.validate_jwt_token(token)

    def test_read_invalid_jwt_token_raises(self) -> None:
        """Test that reading an invalid JWT token raises an error."""
        invalid_token = "invalid"
        with self.assertRaises(jwt.InvalidTokenError):
            AccessService.validate_jwt_token(invalid_token)

    def test_read_expired_jwt_token_raises(self) -> None:
        """Test that reading an expired JWT token raises an error."""
        expired_token = AccessService.create_jwt_token(self.user_id, self.user_name, timedelta(seconds=-1))
        with self.assertRaises(jwt.ExpiredSignatureError):
            AccessService.validate_jwt_token(expired_token)

    def test_read_wrong_issuer_jwt_token_raises(self) -> None:
        """Test that reading a JWT token with a wrong issuer raises an error."""
        token = AccessService.create_jwt_token(self.user_id, self.user_name, self.expiration)
        with self.assertRaises(jwt.InvalidIssuerError):
            jwt.decode(token, os.getenv(JWT_SECRET_ENV), algorithms=["HS256"], issuer="invalid")

    async def test_hash_api_key(self) -> None:
        """Test the API key hash algorithm."""
        user_id = "test-user"
        key_id = "test-key"

        api_key = await AccessService.create_api_key(self, user_id, key_id)
        salt = "mysalt456"

        # Hash should be deterministic
        hash1 = AccessService._hash_api_key(api_key, salt)
        hash2 = AccessService._hash_api_key(api_key, salt)

        self.assertEqual(hash1, hash2)
        self.assertEqual(len(hash1), 64)  # SHA-256 hex digest is 64 characters
        self.assertTrue(all(c in "0123456789abcdef" for c in hash1.lower()))

    async def test_create_api_key(self) -> None:
        """Test the creation of an API key."""
        user_id = "test-user"
        key_id = "test-key"

        # Create an API key
        api_key = await AccessService.create_api_key(self, user_id, key_id)

        # Check if the plain-text key is returned
        self.assertIsInstance(api_key, str)
        self.assertEqual(len(api_key), API_KEY_ID_LENGTH + 1 + API_KEY_LENGTH)

    async def test_validate_api_key_valid(self) -> None:
        """Test that a valid API key can be validated."""
        user_id = "test-user"
        key_id = "test-key"

        # Create API key and get the plain-text key
        api_key = await AccessService.create_api_key(self, user_id, key_id)

        # Validate the API key
        assert await AccessService.validate_api_key(self, api_key) == user_id

    async def test_validate_api_key_invalid(self) -> None:
        """Test that an invalid API key is rejected."""
        user_id = "test-user"
        key_id = "test-key"

        # Create API key and get the plain-text key
        valid_key = await AccessService.create_api_key(self, user_id, key_id)

        # Provide an incorrect API key for validation
        invalid_key = "invalid-test-key"

        assert await AccessService.validate_api_key(self, invalid_key) is None

        # The valid key should still work
        assert await AccessService.validate_api_key(self, valid_key) == user_id

    async def test_revoke_api_key_by_key_id(self) -> None:
        """Test that an API key can be revoked by key_id."""
        user_id = "test-user"
        key_id = "test-key"

        # Create an API key
        await AccessService.create_api_key(self, user_id, key_id)

        # Revoke the API key
        await AccessService.revoke_api_key(self, user_id, key_id)

        # Check that the key was removed
        assert all(api_key.key_id != key_id for api_key in await AccessService.list_api_keys(self, user_id))

    async def test_list_api_keys(self) -> None:
        """Test that we can list API keys for a given user."""
        user_id = "user123"

        # Create some API keys for the user
        await AccessService.create_api_key(self, user_id, "key1")
        await AccessService.create_api_key(self, user_id, "key2")

        # List the API keys
        keys = await AccessService.list_api_keys(self, user_id)

        self.assertEqual(keys[0].key_id, "key1")
        self.assertEqual(keys[1].key_id, "key2")
        self.assertIsNotNone(keys[0].created_at)
        self.assertIsNotNone(keys[1].created_at)

        # Create another key and verify the list updates
        await AccessService.create_api_key(self, user_id, "key3")
        keys = await AccessService.list_api_keys(self, user_id)

        self.assertEqual(keys[0].key_id, "key1")
        self.assertEqual(keys[1].key_id, "key2")
        self.assertEqual(keys[2].key_id, "key3")
        self.assertIsNotNone(keys[0].created_at)
        self.assertIsNotNone(keys[1].created_at)
        self.assertIsNotNone(keys[2].created_at)
