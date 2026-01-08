"""Tests for Auth API handler."""

from unittest.mock import MagicMock

from aiohttp import web

from metadata_backend.api.services.auth import AuthService
from metadata_backend.services.auth_service import AuthServiceHandler


async def test_auth(monkeypatch):
    """Test OIDC authentication flow."""

    mock_oidc_url = "http://mock/oidc"
    mock_auth_url = "http://mock/auth"
    mock_code = "code"
    mock_user_id = "user"
    mock_state = "state"

    monkeypatch.setenv("OIDC_URL", mock_oidc_url)

    handler = AuthServiceHandler()

    # Mock RPHandler.
    mock_rph = MagicMock()
    mock_rph.begin.return_value = mock_auth_url
    mock_rph.get_session_information.return_value = {"iss": mock_oidc_url, "code": mock_code}
    mock_rph.finalize.return_value = {"userinfo": {"sub": mock_user_id}}

    handler._rph = mock_rph

    # Test login.
    resp = await handler.login()
    assert isinstance(resp, web.HTTPSeeOther)
    assert resp.headers["Location"].startswith(mock_auth_url)

    req = MagicMock()
    req.query = {"state": mock_state, "code": mock_code}

    # Test callback.
    resp = await handler.callback(req)
    assert isinstance(resp, web.HTTPSeeOther)
    jwt_token = resp.cookies["access_token"].value

    user_id, user_name = AuthService.validate_jwt_token(jwt_token)
    assert user_id == mock_user_id
    assert user_name == mock_user_id

    assert resp.headers["Location"].endswith("/home")

    # Ensure RPHandler methods were called correctly.
    mock_rph.begin.assert_called_once_with("aai")
    mock_rph.get_session_information.assert_called_once_with(mock_state)
    mock_rph.finalize.assert_called_once_with(mock_oidc_url, {"iss": mock_oidc_url, "code": mock_code})
