"""Tests for Auth API handler."""

from unittest.mock import MagicMock

from aiohttp import web

from metadata_backend.api.handlers.auth import AuthAPIHandler
from metadata_backend.api.services.auth import AuthService
from metadata_backend.server import get_auth_routes
from metadata_backend.services.auth_service import AuthServiceHandler


async def test_auth(aiohttp_client, monkeypatch):
    # Mock OIDC_URL.
    mock_oidc_url = "http://mock/oidc"
    mock_auth_url = "http://mock/auth"
    monkeypatch.setenv("OIDC_URL", mock_oidc_url)

    # Create AuthServiceHandler.
    service_handler = AuthServiceHandler()

    # Mock RPHandler.
    mock_rph = MagicMock()
    mock_rph.begin.return_value = mock_auth_url
    mock_rph.get_session_information.return_value = {"code": "code"}
    mock_rph.finalize.return_value = {"userinfo": {"sub": "user"}}
    service_handler._rph = mock_rph

    # Create API handler and replace its service handler
    auth = AuthAPIHandler(service_handler)

    # Create web app and auth routes.
    app = web.Application()
    app.add_routes(get_auth_routes(auth, "CSC"))

    client = await aiohttp_client(app)

    # Test /login endpoint.
    resp = await client.get("/login", allow_redirects=False)
    assert resp.status == 303
    assert resp.headers["Location"] == mock_auth_url
    mock_rph.begin.assert_called_once_with("aai")

    # Test /callback endpoint.
    resp = await client.get("/callback", params={"state": "state", "code": "code"}, allow_redirects=False)
    assert resp.status == 303
    assert resp.headers["Location"].endswith("/home")
    assert "access_token" in resp.cookies
    jwt_token = resp.cookies["access_token"].value

    user_id, user_name = AuthService.validate_jwt_token(jwt_token)
    assert user_id == "user"
    assert user_name == "user"

    # Ensure RPHandler methods were called correctly.
    mock_rph.get_session_information.assert_called_once_with("state")
    mock_rph.finalize.assert_called_once_with(mock_oidc_url, {"code": "code"})
