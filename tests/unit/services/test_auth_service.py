"""Tests for Auth API handler."""

import asyncio
import hashlib
import json
import threading
from base64 import urlsafe_b64encode
from http.cookies import SimpleCookie
from unittest.mock import MagicMock
from urllib.parse import parse_qs

import jwt as pyjwt
import pytest
import requests
from fastapi import HTTPException
from fastapi.responses import RedirectResponse
from idpyoidc.client.exception import OidcServiceError
from requests import PreparedRequest, Response, Session
from requests.adapters import HTTPAdapter
from starlette import status

from metadata_backend.api.services.auth import AuthService
from metadata_backend.services.auth_service import AuthServiceHandler, DPoPHandler, dpop_request
from tests.unit.patches.auth_service import (
    MockDPoPHandler,
    mock_response,
    patch_async_client,
)


@pytest.fixture
def mock_oidc_url(monkeypatch) -> str:
    url = "http://mockauth:8005"
    monkeypatch.setenv("OIDC_URL", url)
    return url


@pytest.fixture
def async_client(monkeypatch):
    def _factory(responses: list[MagicMock]) -> MagicMock:
        return patch_async_client(monkeypatch, responses)

    return _factory


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
    mock_rph.get_valid_access_token.return_value = ("oidc-access-token", 0)

    handler._rph = mock_rph

    # Test login.
    resp = await handler.get_oidc_auth_url()
    assert resp == mock_auth_url

    # Test callback.
    jwt_token, oidc_access_token, oidc_exp_time = await handler.callback(mock_state, mock_code)
    resp = await handler.initiate_web_session(jwt_token, oidc_access_token, oidc_exp_time)
    assert isinstance(resp, RedirectResponse)
    cookie = SimpleCookie()
    set_cookie_headers = [
        value.decode("utf-8") for key, value in resp.raw_headers if key.decode("utf-8").lower() == "set-cookie"
    ]
    for header in set_cookie_headers:
        cookie.load(header)
    jwt_cookie = cookie["access_token"].value
    oidc_cookie = cookie["oidc_access_token"].value
    assert jwt_cookie == jwt_token
    assert oidc_cookie == oidc_access_token

    user_id, user_name = AuthService.validate_jwt_token(jwt_cookie)
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


async def test_dpop_request(dpop_test_jwks, monkeypatch):
    """Test that DPoP requests add DPoP header and convert Bearer to DPoP."""
    handler = DPoPHandler()

    # Mock requests.request to track both token and userinfo calls
    server_nonce = "server-provided-nonce-123"
    mock_response = MagicMock()
    mock_response.headers = {"DPoP-Nonce": server_nonce}
    mock_request = MagicMock(return_value=mock_response)
    monkeypatch.setattr("metadata_backend.services.auth_service.requests.request", mock_request)

    # Test 1: Token endpoint adds DPoP header and extracts nonce
    token_headers = {"Content-Type": "application/x-www-form-urlencoded"}
    handler.request("POST", "https://oidc.example.com/token", data={}, headers=token_headers)
    sent_headers = mock_request.call_args.kwargs["headers"]
    assert len(sent_headers["DPoP"]) > 0
    assert sent_headers["Content-Type"] == "application/x-www-form-urlencoded"
    assert "DPoP" not in token_headers  # The caller's headers are not modified
    assert handler.nonce == server_nonce

    # Test 2: Userinfo endpoint uses extracted nonce and converts Bearer to DPoP
    access_token = "test_access_token"
    handler.request(
        "GET", "https://oidc.example.com/userinfo", headers={"Authorization": f"Bearer {access_token}"}, verify=True
    )
    sent_headers = mock_request.call_args.kwargs["headers"]
    assert mock_request.call_args.kwargs["verify"] is True

    # Verify Authorization header changed from Bearer to DPoP
    assert sent_headers["Authorization"] == f"DPoP {access_token}"

    # Verify DPoP header was added with ath claim and nonce from token endpoint
    payload_dict = pyjwt.decode(sent_headers["DPoP"], options={"verify_signature": False})
    assert "ath" in payload_dict  # Should have access token binding
    assert payload_dict["nonce"] == server_nonce  # Should use nonce from token response

    # requests.request was called once for /token, once for /userinfo
    assert mock_request.call_count == 2


async def test_dpop_request_outside_login(dpop_test_jwks, monkeypatch):
    """Test that idpyoidc requests outside an OIDC login are sent without DPoP headers."""
    mock_request = MagicMock()
    monkeypatch.setattr("metadata_backend.services.auth_service.requests.request", mock_request)

    dpop_request("POST", "https://oidc.example.com/token", headers={})

    mock_request.assert_called_once_with("POST", "https://oidc.example.com/token", headers={})


async def test_get_pouta_access_token_from_userinfo_success(mock_oidc_url, async_client, monkeypatch):
    client = async_client([mock_response(200, {"pouta_access_token": "pouta-token"})])

    monkeypatch.setattr(
        "metadata_backend.services.auth_service.DPoPHandler",
        MockDPoPHandler,
    )

    token = await AuthServiceHandler.get_pouta_access_token_from_userinfo("oidc-token")
    assert token == "pouta-token"
    assert client.get.await_count == 1


async def test_get_pouta_access_token_from_userinfo_retries_with_nonce(mock_oidc_url, async_client, monkeypatch):
    """Test that a 401 response with DPoP-Nonce triggers a retry with the nonce."""
    client = async_client(
        [
            mock_response(status.HTTP_401_UNAUTHORIZED, headers={"DPoP-Nonce": "nonce-1"}),
            mock_response(200, {"pouta_access_token": "pouta-token"}),
        ]
    )

    monkeypatch.setattr("metadata_backend.services.auth_service.DPoPHandler", MockDPoPHandler)

    token = await AuthServiceHandler.get_pouta_access_token_from_userinfo("oidc-token")
    assert token == "pouta-token"
    assert client.get.await_count == 2


async def test_get_pouta_access_token_from_userinfo_missing_oidc_token():
    """Test that missing OIDC access token raises HTTPException."""
    try:
        await AuthServiceHandler.get_pouta_access_token_from_userinfo("")
    except HTTPException as ex:
        assert ex.status_code == status.HTTP_401_UNAUTHORIZED
        assert ex.detail == "Missing OIDC access token"
    else:
        raise AssertionError("Expected HTTPException")


async def test_get_pouta_access_token_from_userinfo_upstream_error(mock_oidc_url, async_client, monkeypatch):
    """Test that a 500 response from the upstream server triggers a 401 HTTPException."""
    async_client([mock_response(status.HTTP_500_INTERNAL_SERVER_ERROR)])

    monkeypatch.setattr("metadata_backend.services.auth_service.DPoPHandler", MockDPoPHandler)

    try:
        await AuthServiceHandler.get_pouta_access_token_from_userinfo("oidc-token")
    except HTTPException as ex:
        assert ex.status_code == status.HTTP_401_UNAUTHORIZED
    else:
        raise AssertionError("Expected HTTPException")


def test_concurrent_dpop_callbacks(csc_client, dpop_test_jwks, monkeypatch):
    """Test that overlapping OIDC callbacks each send their own DPoP proofs."""

    issuer = "http://mock/oidc"
    token_url = f"{issuer}/token"
    userinfo_url = f"{issuer}/userinfo"
    codes = ["code-a", "code-b"]

    monkeypatch.setenv("OIDC_URL", issuer)
    monkeypatch.setenv("OIDC_DPOP", "true")

    handler = AuthServiceHandler()
    rph = handler.rph

    # Both logins wait here on their first token request, so that their finalize calls overlap.
    overlap = threading.Barrier(len(codes), timeout=5)
    proofs: dict[str, list[dict]] = {code: [] for code in codes}

    def idp(adapter: HTTPAdapter, request: PreparedRequest, **_: object) -> Response:
        """Mock IdP that requires a DPoP nonce of its own for each login."""
        if request.url == token_url:
            code = parse_qs(request.body)["code"][0]
            access_token = None
        else:
            access_token = request.headers["Authorization"].removeprefix("DPoP ")
            code = access_token.removeprefix("token-")
        proof = pyjwt.decode(request.headers["DPoP"], options={"verify_signature": False})
        proofs[code].append(proof)

        response = Response()
        response.headers["DPoP-Nonce"] = f"nonce-{code}"
        if len(proofs[code]) == 1:
            overlap.wait()
        if proof["nonce"] != f"nonce-{code}":
            response.status_code = status.HTTP_400_BAD_REQUEST
            response._content = json.dumps({"error": "use_dpop_nonce"}).encode()
        else:
            response.status_code = status.HTTP_200_OK
            response._content = json.dumps({"access_token": f"token-{code}", "sub": code}).encode()
        return response

    monkeypatch.setattr(HTTPAdapter, "send", idp)

    def finalize(_issuer: str, session_info: dict) -> dict:
        """Mock of RPHandler.finalize that sends its requests as idpyoidc does."""
        httpc = rph.httpc or requests.request
        code = session_info["code"]
        token = httpc("POST", token_url, data={"code": code}, headers={}, **rph.httpc_params)
        if token.status_code != status.HTTP_200_OK:
            raise OidcServiceError(token.text)
        access_token = token.json()["access_token"]
        userinfo = httpc("GET", userinfo_url, headers={"Authorization": f"Bearer {access_token}"}, **rph.httpc_params)
        return {"userinfo": userinfo.json()}

    monkeypatch.setattr(rph, "get_session_information", lambda state: {"iss": issuer})
    monkeypatch.setattr(rph, "finalize", finalize)
    monkeypatch.setattr(rph, "get_valid_access_token", lambda state: (f"token-{state}", 0))

    original_session_request = Session.request
    monkeypatch.setattr(Session, "request", original_session_request)  # Restored even if a login leaks a patch
    results: dict[str, object] = {}

    def login(code: str) -> None:
        try:
            results[code] = asyncio.run(handler.callback(code, code))
        except Exception as e:
            results[code] = e

    threads = [threading.Thread(target=login, args=(code,)) for code in codes]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert Session.request is original_session_request
    for code in codes:
        assert not isinstance(results[code], Exception), results[code]
        _, access_token, _ = results[code]
        assert access_token == f"token-{code}"

        # First token request without nonce, the retry and userinfo with this login's own nonce.
        assert [p["htu"] for p in proofs[code]] == [token_url, token_url, userinfo_url]
        assert [p["nonce"] for p in proofs[code]] == [None, f"nonce-{code}", f"nonce-{code}"]
        assert "ath" not in proofs[code][1]
        assert proofs[code][2]["ath"] == (
            urlsafe_b64encode(hashlib.sha256(f"token-{code}".encode()).digest()).decode().rstrip("=")
        )
