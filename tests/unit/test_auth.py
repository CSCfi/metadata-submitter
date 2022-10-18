"""Test API auth endpoints."""
import time
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp_session
from aiohttp.test_utils import AioHTTPTestCase
from aiohttp.web_exceptions import (
    HTTPBadRequest,
    HTTPInternalServerError,
    HTTPSeeOther,
    HTTPUnauthorized,
)

from metadata_backend.api.auth import AccessHandler
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
        with patch("oidcrp.rp_handler.RPHandler.begin", side_effect=Exception):
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
        with patch("oidcrp.rp_handler.RPHandler.get_session_information", side_effect=KeyError), self.p_get_sess:
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
        """Test login fails due to bad OIDCRP config."""
        # OIDCRP init fails, because AAI config endpoint request fails
        request = Mock_Request()
        with self.assertRaises(HTTPInternalServerError):
            await self.AccessHandler.login(request)

    async def test_login_pass(self):
        """Test login redirects user."""
        response = {"url": "some url"}
        request = Mock_Request()
        with patch("oidcrp.rp_handler.RPHandler.begin", return_value=response):
            response = await self.AccessHandler.login(request)
            assert isinstance(response, HTTPSeeOther)

    async def test_callback_pass_csc(self):
        """Test callback correct validation (CSC format)."""
        request = Mock_Request()
        request.query["state"] = "state"
        request.query["code"] = "code"

        session = {"iss": "http://auth.domain.com:5430", "auth_request": {}}
        finalize = {
            "token": "token",
            "userinfo": {"sub": "user", "given_name": "name", "family_name": "name", "sdSubmitProjects": "1000 2000"},
        }
        db_client = MagicMock()
        db_database = MagicMock()
        db_collection = AsyncMock()
        db_client.__getitem__.return_value = db_database
        db_database.__getitem__.return_value = db_collection

        request.app["db_client"] = db_client

        with patch("oidcrp.rp_handler.RPHandler.get_session_information", return_value=session):
            with patch("oidcrp.rp_handler.RPHandler.finalize", return_value=finalize):
                with patch("metadata_backend.api.auth.AccessHandler._set_user", return_value=None):
                    with self.p_new_sess:
                        await self.AccessHandler.callback(request)

    async def test_callback_pass_ls(self):
        """Test callback correct validation (LS format)."""
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
                "eduperson_entitlement": ["group1", "group2"],
            },
        }
        db_client = MagicMock()
        db_database = MagicMock()
        db_collection = AsyncMock()
        db_client.__getitem__.return_value = db_database
        db_database.__getitem__.return_value = db_collection

        request.app["db_client"] = db_client

        with patch("oidcrp.rp_handler.RPHandler.get_session_information", return_value=session):
            with patch("oidcrp.rp_handler.RPHandler.finalize", return_value=finalize):
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

        with patch("oidcrp.rp_handler.RPHandler.get_session_information", return_value=session):
            with patch("oidcrp.rp_handler.RPHandler.finalize", return_value=finalize):
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
        with patch("oidcrp.rp_handler.RPHandler.get_session_information", return_value=session):
            with patch("oidcrp.rp_handler.RPHandler.finalize", return_value=finalize):
                with self.assertRaises(HTTPUnauthorized):
                    await self.AccessHandler.callback(request)

    async def test_callback_fail_finalize(self):
        """Test callback fail finalize."""
        request = Mock_Request()
        request.query["state"] = "state"
        request.query["code"] = "code"

        session = {"iss": "http://auth.domain.com:5430", "auth_request": {}}
        with patch("oidcrp.rp_handler.RPHandler.get_session_information", return_value=session):
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
