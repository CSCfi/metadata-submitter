"""Test API auth endpoints."""

import os
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock, patch

from aiohttp.test_utils import AioHTTPTestCase
from aiohttp.web_exceptions import HTTPBadRequest, HTTPInternalServerError, HTTPSeeOther, HTTPUnauthorized

from metadata_backend.api.auth import AccessHandler
from metadata_backend.api.services.auth import (
    JWT_SECRET_ENV,
)
from metadata_backend.server import init
from metadata_backend.api.resources import set_resource, ResourceType

from .mockups import Mock_Request

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

        set_resource(request.app, ResourceType.MONGO_CLIENT, db_client)

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

        set_resource(request.app, ResourceType.MONGO_CLIENT, db_client)

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
