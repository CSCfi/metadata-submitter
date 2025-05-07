"""Test API auth endpoints."""

from datetime import timedelta
import os
import time
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, MagicMock, patch

import jwt
import aiohttp_session
from aiohttp.test_utils import AioHTTPTestCase
from aiohttp.web_exceptions import HTTPBadRequest, HTTPInternalServerError, HTTPSeeOther, HTTPUnauthorized

from metadata_backend.api.auth import AccessHandler
from metadata_backend.api.services.auth import (
    API_KEY_LENGTH,
    JWT_ALGORITHM,
    JWT_ISSUER,
    JWT_SECRET_ENV,
    AccessService
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

        self.session_return = aiohttp_session.Session(
            "test-identity",
            new=True,
            data={},
        )

        self.session_return["access_token"] = "not-really-a-token"  # nosec
        self.session_return["at"] = time.time()
        self.session_return["user_info"] = "value"
        self.session_return["oidc_state"] = "state"

        self.aiohttp_session_get_session_mock = AsyncMock()
        self.aiohttp_session_get_session_mock.return_value = self.session_return
        self.p_get_sess = patch(
            "metadata_backend.api.auth.aiohttp_session.get_session",
            self.aiohttp_session_get_session_mock,
        )
        self.aiohttp_session_new_session_mock = AsyncMock()
        self.p_new_sess = patch(
            "metadata_backend.api.auth.aiohttp_session.new_session",
            self.aiohttp_session_new_session_mock,
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
            self.p_get_sess,
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

        self.session_return = aiohttp_session.Session(
            "test-identity",
            new=True,
            data={},
        )

        self.session_return["access_token"] = "not-really-a-token"  # nosec
        self.session_return["at"] = time.time()
        self.session_return["user_info"] = "value"
        self.session_return["oidc_state"] = "state"

        self.aiohttp_session_get_session_mock = AsyncMock()
        self.aiohttp_session_get_session_mock.return_value = self.session_return
        self.p_get_sess = patch(
            "metadata_backend.api.auth.aiohttp_session.get_session",
            self.aiohttp_session_get_session_mock,
        )

        self.aiohttp_session_new_session_mock = AsyncMock()
        self.p_new_sess = patch(
            "metadata_backend.api.auth.aiohttp_session.new_session",
            self.aiohttp_session_new_session_mock,
        )

    def tearDown(self):
        """Cleanup mocked stuff."""
        pass

    async def test_set_user(self):
        """Test set user success."""
        request = Mock_Request()
        session_id = aiohttp_session.Session(
            "test-identity",
            new=True,
            data={},
        )
        new_user_id = "USR12345"

        db_client = MagicMock()
        db_database = MagicMock()
        db_collection = AsyncMock()
        db_client.__getitem__.return_value = db_database
        db_database.__getitem__.return_value = db_collection

        request.app["db_client"] = db_client
        user_data = {"sub": "user@test.fi", "given_name": "User", "family_name": "Test", "projects": "x_files, memes"}

        with patch("metadata_backend.api.operators.user.UserOperator.create_user", return_value=new_user_id):
            await self.AccessHandler._set_user(request, session_id, user_data)

        self.assertIn("user_info", session_id)
        self.assertEqual(new_user_id, session_id["user_info"])

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
                with patch("metadata_backend.api.auth.AccessHandler._set_user", return_value=None):
                    with self.p_new_sess:
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
                with patch("metadata_backend.api.auth.AccessHandler._set_user", return_value=None):
                    with self.p_new_sess:
                        await self.AccessHandler.callback(request)

    async def test_callback_fail_no_projects(self):
        """Test callback fails when user has not project group affiliations."""
        request = Mock_Request()
        request.query["state"] = "state"
        request.query["code"] = "code"

        session = {"iss": "http://auth.domain.com:5430", "auth_request": {}}
        finalize = {
            "token": "token",
            "userinfo": {
                "sub": "user",
                "given_name": "name",
                "family_name": "name",
            },
        }

        with patch("idpyoidc.client.rp_handler.RPHandler.get_session_information", return_value=session):
            with patch("idpyoidc.client.rp_handler.RPHandler.finalize", return_value=finalize):
                with self.assertRaises(HTTPUnauthorized):
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

    async def test_create_user_data_pass(self):
        """Test that user data is correctly parsed from userinfo."""
        userinfo = {"sub": "user", "given_name": "given", "family_name": "family"}
        user_data = await AccessHandler._create_user_data(self, userinfo)
        assert user_data["user_id"] == "user"
        assert user_data["real_name"] == "given family"
        assert user_data["projects"] == []

    async def test_create_user_data_fail(self):
        """Test that user data parsing raises an error if data is missing."""
        userinfo = {"given_name": "given", "family_name": "family"}
        with self.assertRaises(HTTPUnauthorized):
            await AccessHandler._create_user_data(self, userinfo)

    async def test_get_projects_from_userinfo_pass(self):
        """Test that projects are correctly parsed from userinfo."""
        userinfo = {"sdSubmitProjects": "1000", "eduperson_entitlement": ["group"]}
        projects = await AccessHandler._get_projects_from_userinfo(self, userinfo)
        assert projects[0]["project_name"] == "1000"
        assert projects[0]["project_origin"] == "csc"
        assert projects[1]["project_name"] == "group"
        assert projects[1]["project_origin"] == "lifescience"

    async def test_get_projects_from_userinfo_fail(self):
        """Test that no projects raises an error."""
        userinfo = {}
        with self.assertRaises(HTTPUnauthorized):
            await AccessHandler._get_projects_from_userinfo(self, userinfo)


class AccessServiceTestCase(TestCase):
    """Test Auth API services."""

    def setUp(self) -> None:
        self.user_id = "test-user"
        self.expiration = timedelta(minutes=10)
        self.jwt_secret = "test-secret"
        self.jwt_secret_env = os.getenv(JWT_SECRET_ENV)
        os.environ[JWT_SECRET_ENV] = self.jwt_secret

    def tearDown(self) -> None:
        if self.jwt_secret_env is not None:
            os.environ[JWT_SECRET_ENV] = self.jwt_secret_env

    def test_create_jwt_token_contains_required_claims(self) -> None:
        token = AccessService.create_jwt_token(self.user_id, self.expiration)
        decoded = jwt.decode(token, self.jwt_secret, algorithms=[JWT_ALGORITHM], issuer=JWT_ISSUER)

        self.assertEqual(decoded["sub"], self.user_id)
        self.assertEqual(decoded["iss"], JWT_ISSUER)
        self.assertIn("exp", decoded)
        self.assertIn("iat", decoded)

    def test_read_jwt_token_returns_user_id(self) -> None:
        token = AccessService.create_jwt_token(self.user_id, self.expiration)
        user_id = AccessService.read_jwt_token(token)
        self.assertEqual(user_id, self.user_id)

    def test_create_jwt_token_missing_secret_raises(self) -> None:
        os.environ.pop(JWT_SECRET_ENV, None)
        with self.assertRaises(RuntimeError):
            AccessService.create_jwt_token(self.user_id, self.expiration)

    def test_read_jwt_token_missing_secret_raises(self) -> None:
        token = AccessService.create_jwt_token(self.user_id, self.expiration)
        os.environ.pop(JWT_SECRET_ENV, None)
        with self.assertRaises(RuntimeError):
            AccessService.read_jwt_token(token)

    def test_read_invalid_jwt_token_raises(self) -> None:
        invalid_token = "invalid"
        with self.assertRaises(jwt.InvalidTokenError):
            AccessService.read_jwt_token(invalid_token)

    def test_read_expired_jwt_token_raises(self) -> None:
        expired_token = AccessService.create_jwt_token(self.user_id, timedelta(seconds=-1))
        with self.assertRaises(jwt.ExpiredSignatureError):
            AccessService.read_jwt_token(expired_token)

    def test_read_wrong_issuer_jwt_token_raises(self) -> None:
        token = AccessService.create_jwt_token(self.user_id, self.expiration)

        with self.assertRaises(jwt.InvalidIssuerError):
            jwt.decode(
                token,
                os.getenv(JWT_SECRET_ENV),
                algorithms=["HS256"],
                issuer="invalid"
            )

    def test_hash_api_key(self) -> None:
        """Test the API key hash algorithm."""

        service = AccessService()

        user_id = "test-user"
        key_id = "test-key"

        api_key = service.create_api_key(user_id, key_id)
        salt = "mysalt456"

        # Hash should be deterministic
        hash1 = service._hash_api_key(api_key, salt)
        hash2 = service._hash_api_key(api_key, salt)

        self.assertEqual(hash1, hash2)
        self.assertEqual(len(hash1), 64)  # SHA-256 hex digest is 64 characters
        self.assertTrue(all(c in "0123456789abcdef" for c in hash1.lower()))

    def test_create_api_key(self) -> None:
        """Test the creation of an API key."""

        service = AccessService()

        user_id = "test-user"
        key_id = "test-key"

        # Create an API key
        api_key = service.create_api_key(user_id, key_id)

        # Check if the plain-text key is returned
        self.assertIsInstance(api_key, str)
        self.assertEqual(len(api_key), API_KEY_LENGTH)

    def test_validate_api_key_valid(self) -> None:
        """Test that a valid API key can be validated."""

        service = AccessService()

        user_id = "test-user"
        key_id = "test-key"

        # Create API key and get the plain-text key
        api_key = service.create_api_key(user_id, key_id)

        # Validate the API key
        is_valid = service.validate_api_key(user_id, api_key)

        self.assertTrue(is_valid)

    def test_validate_api_key_invalid(self) -> None:
        """Test that an invalid API key is rejected."""

        service = AccessService()

        user_id = "test-user"
        key_id = "test-key"

        # Create API key and get the plain-text key
        valid_key = service.create_api_key(user_id, key_id)

        # Provide an incorrect API key for validation
        invalid_key = "invalid-test-key"

        is_valid = service.validate_api_key(user_id, invalid_key)

        self.assertFalse(is_valid)

        # The valid key should still work
        is_valid = service.validate_api_key(user_id, valid_key)
        self.assertTrue(is_valid)

    def test_revoke_api_key_by_key_id(self) -> None:
        """Test that an API key can be revoked by key_id."""

        service = AccessService()

        user_id = "test-user"
        key_id = "test-key"

        # Create an API key
        service.create_api_key(user_id, key_id)

        # Revoke the API key
        revoked = service.revoke_api_key(user_id, key_id)

        self.assertTrue(revoked)

        # Check if the key is actually removed
        self.assertNotIn(key_id, service.api_keys[user_id])

    def test_revoke_api_key_by_api_key(self) -> None:
        """Test that an API key can be revoked by the plain-text API key."""

        service = AccessService()

        user_id = "test-user"
        key_id = "test-key"

        # Create an API key
        api_key = service.create_api_key(user_id, key_id)

        # Revoke the API key by passing the plain-text key
        revoked = service.revoke_api_key(user_id, api_key)

        self.assertTrue(revoked)

        # Check if the key is actually removed
        self.assertNotIn(key_id, service.api_keys[user_id])

    def test_list_api_keys(self) -> None:
        """Test that we can list API keys for a given user."""

        service = AccessService()

        user_id = "user123"

        # Create some API keys for the user
        service.create_api_key(user_id, "key1")
        service.create_api_key(user_id, "key2")

        # List the API keys
        keys = service.list_api_keys(user_id)

        self.assertEqual(keys, ["key1", "key2"])

        # Create another key and verify the list updates
        service.create_api_key(user_id, "key3")
        keys = service.list_api_keys(user_id)

        self.assertEqual(keys, ["key1", "key2", "key3"])
