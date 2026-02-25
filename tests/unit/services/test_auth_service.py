"""Tests for Auth API handler."""

import hashlib
import json
from base64 import urlsafe_b64encode
from http.cookies import SimpleCookie
from unittest.mock import MagicMock

import jwt as pyjwt
from fastapi.responses import RedirectResponse
from requests import Session

from metadata_backend.api.services.auth import AuthService
from metadata_backend.services.auth_service import AuthServiceHandler, DPoPHandler


async def test_auth(csc_client, dpop_test_jwks, monkeypatch):
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
    resp = await handler.get_oidc_auth_url()
    assert resp == mock_auth_url

    # Test callback.
    jwt, userinfo = await handler.callback(mock_state, mock_code)
    resp = await handler.initiate_web_session(jwt, userinfo)
    assert isinstance(resp, RedirectResponse)
    cookie = SimpleCookie()
    cookie.load(resp.headers.get("set-cookie"))
    jwt_token = cookie["access_token"].value
    assert jwt_token == jwt

    user_id, user_name = AuthService.validate_jwt_token(jwt_token)
    assert user_id == mock_user_id
    assert user_name == mock_user_id

    assert resp.headers["Location"] is not None

    # Ensure RPHandler methods were called correctly.
    mock_rph.begin.assert_called_once_with("aai")
    mock_rph.get_session_information.assert_called_once_with(mock_state)
    mock_rph.finalize.assert_called_once_with(mock_oidc_url, {"iss": mock_oidc_url, "code": mock_code})


async def test_dpop_proof_generation(dpop_test_jwks):
    """Test DPoP proof JWT generation and structure."""
    handler = DPoPHandler()

    assert handler.nonce is None
    assert handler.private_key is not None
    assert "d" not in handler.public_jwk

    # Generate proof for token endpoint
    proof = handler.generate_proof("POST", "https://oidc.example.com/token")

    # Verify JWT structure
    assert isinstance(proof, str)
    assert len(proof.split(".")) == 3

    # Decode and verify payload
    parts = proof.split(".")
    payload = pyjwt.utils.base64url_decode(parts[1] + "==")
    payload_dict = json.loads(payload)

    # Verify required RFC 9449 claims
    assert payload_dict["htm"] == "POST"
    assert payload_dict["htu"] == "https://oidc.example.com/token"
    assert "jti" in payload_dict
    assert "iat" in payload_dict
    assert payload_dict["nonce"] is None  # Initially null

    # Set server nonce
    server_nonce = "server-nonce-value"
    handler.nonce = server_nonce

    # Generate proof with access token (for userinfo endpoint)
    access_token = "test_access_token"
    proof = handler.generate_proof("GET", "https://oidc.example.com/userinfo", access_token=access_token)

    # Decode and verify payload
    parts = proof.split(".")
    payload = pyjwt.utils.base64url_decode(parts[1] + "==")
    payload_dict = json.loads(payload)

    # Verify nonce is included
    assert payload_dict["nonce"] == server_nonce

    # Verify ath claim (access token hash)
    expected_ath = urlsafe_b64encode(hashlib.sha256(access_token.encode()).digest()).decode().rstrip("=")
    assert payload_dict["ath"] == expected_ath


async def test_patched_request(dpop_test_jwks):
    """Test that patched request adds DPoP header and converts Bearer to DPoP."""
    original_session_request = Session.request
    handler = DPoPHandler()

    handler.setup_http_interception()
    original_request = handler._original_request  # Save original request method

    try:
        # Mock the original request to track both token and userinfo calls
        mock_session = MagicMock(spec=Session)
        server_nonce = "server-provided-nonce-123"
        mock_response = MagicMock()
        mock_response.headers = {"DPoP-Nonce": server_nonce}
        mock_original_request = MagicMock(return_value=mock_response)
        handler._original_request = mock_original_request

        # Test 1: Token endpoint adds DPoP header and extracts nonce
        token_kwargs = {"headers": {}}
        handler._patched_request(mock_session, "POST", "https://oidc.example.com/token", **token_kwargs)
        assert "DPoP" in token_kwargs["headers"]
        assert len(token_kwargs["headers"]["DPoP"]) > 0
        assert handler.nonce == server_nonce

        # Test 2: Userinfo endpoint uses extracted nonce and converts Bearer to DPoP
        access_token = "test_access_token"
        userinfo_kwargs = {"headers": {"Authorization": f"Bearer {access_token}"}}
        handler._patched_request(mock_session, "GET", "https://oidc.example.com/userinfo", **userinfo_kwargs)

        # Verify Authorization header changed from Bearer to DPoP
        assert userinfo_kwargs["headers"]["Authorization"].startswith("DPoP ")
        assert access_token in userinfo_kwargs["headers"]["Authorization"]

        # Verify DPoP header was added with ath claim and nonce from token endpoint
        assert "DPoP" in userinfo_kwargs["headers"]
        proof = userinfo_kwargs["headers"]["DPoP"]
        parts = proof.split(".")
        payload = pyjwt.utils.base64url_decode(parts[1] + "==")
        payload_dict = json.loads(payload)
        assert "ath" in payload_dict  # Should have access token binding
        assert payload_dict["nonce"] == server_nonce  # Should use nonce from token response

        # Original request was called once for /token, once for /userinfo
        assert mock_original_request.call_count == 2
    finally:
        handler._original_request = original_request  # Restore original request method (not mock)
        handler.teardown_http_interception()
        assert Session.request == original_session_request
