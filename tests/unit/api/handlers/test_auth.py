"""Tests for Auth API handler."""

from unittest.mock import MagicMock, PropertyMock, patch

from metadata_backend.api.services.auth import AuthService
from metadata_backend.conf.oidc import oidc_config
from metadata_backend.services.auth_service import AuthServiceHandler


async def test_auth(csc_client, dpop_test_jwks, monkeypatch):
    # Mock RPHandler.
    mock_rph = MagicMock()
    mock_auth_url = "http://mock/auth"
    mock_rph.begin.return_value = mock_auth_url
    mock_rph.get_session_information.return_value = {"code": "code"}
    mock_rph.finalize.return_value = {"userinfo": {"sub": "user"}}

    with patch.object(AuthServiceHandler, "rph", new_callable=PropertyMock) as mock_prop:
        mock_prop.return_value = mock_rph
        # Test /login endpoint.
        resp = csc_client.get("/login", follow_redirects=False)
        assert resp.status_code == 303
        assert resp.headers["Location"] == mock_auth_url
        mock_rph.begin.assert_called_once_with("aai")

        # Test /callback endpoint.
        resp = csc_client.get("/callback", params={"state": "state", "code": "code"}, follow_redirects=False)
        assert resp.status_code == 303
        assert resp.headers["Location"].endswith("/home")
        assert "access_token" in resp.cookies
        jwt_token = resp.cookies["access_token"]

        user_id, user_name = AuthService.validate_jwt_token(jwt_token)
        assert user_id == "user"
        assert user_name == "user"

        # Ensure RPHandler methods were called correctly.
        mock_rph.get_session_information.assert_called_once_with("state")
        mock_rph.finalize.assert_called_once_with(oidc_config().OIDC_URL, {"code": "code"})
