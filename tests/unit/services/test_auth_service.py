"""Tests for Auth API handler."""

import asyncio
import hashlib
import json
import threading
import time
from base64 import urlsafe_b64encode
from http.cookies import SimpleCookie
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from urllib.parse import parse_qs

import jwt as pyjwt
import pytest
import requests
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import HTTPException
from fastapi.responses import RedirectResponse
from idpyoidc.client.exception import OidcServiceError
from idpyoidc.message import oidc
from jwt.algorithms import ECAlgorithm
from requests import PreparedRequest, Response
from requests.adapters import HTTPAdapter
from starlette import status
from yarl import URL

from metadata_backend.api.exceptions import ServiceHandlerSystemException
from metadata_backend.api.services.auth import AuthService
from metadata_backend.services.auth_service import AuthServiceHandler, DPoPHandler, dpop_request


@pytest.fixture
def mock_oidc_url(monkeypatch) -> str:
    url = "http://mockauth:8005"
    monkeypatch.setenv("OIDC_URL", url)
    return url


@pytest.fixture
def userinfo_requests(monkeypatch):
    """Mock requests.request, which sends the Pouta userinfo request, with the given responses."""

    def _factory(*responses: Response) -> MagicMock:
        mock_request = MagicMock(side_effect=list(responses))
        monkeypatch.setattr("metadata_backend.services.auth_service.requests.request", mock_request)
        return mock_request

    return _factory


@pytest.fixture
def pouta_handler(mock_oidc_url, dpop_test_jwks, monkeypatch) -> AuthServiceHandler:
    """AuthServiceHandler with DPoP that has already fetched the provider's discovery document."""
    monkeypatch.setenv("OIDC_DPOP", "true")
    handler = AuthServiceHandler()
    handler._provider_info = {
        "token_endpoint": f"{mock_oidc_url}/token",
        "userinfo_endpoint": f"{mock_oidc_url}/userinfo",
    }
    return handler


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
    mock_rph.init_authorization.return_value = f"{mock_auth_url}?state={mock_state}"
    mock_rph.get_session_information.return_value = {"iss": mock_oidc_url, "code": mock_code}
    mock_rph.finalize.return_value = {"userinfo": {"sub": mock_user_id}}
    mock_rph.get_valid_access_token.return_value = ("oidc-access-token", 0)

    handler._rph = mock_rph

    # Test login.
    resp = await handler.begin_login()
    assert resp == f"{mock_auth_url}?state={mock_state}"
    assert list(handler._login_started) == [mock_state]

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
    mock_rph.client_setup.assert_called_once_with("aai")
    mock_rph.init_authorization.assert_called_once_with(client=mock_rph.client_setup.return_value)
    # The callback removed the login's state
    mock_rph.clear_session.assert_called_once_with(mock_state)
    assert handler._login_started == {}
    mock_rph.get_session_information.assert_called_once_with(mock_state)
    mock_rph.finalize.assert_called_once_with(mock_oidc_url, {"iss": mock_oidc_url, "code": mock_code})


async def test_dpop_proof_generation(dpop_test_jwks):
    """Test DPoP proof JWT generation and structure."""
    handler = DPoPHandler(
        token_endpoint="https://oidc.example.com/token", userinfo_endpoint="https://oidc.example.com/userinfo"
    )

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
    handler = DPoPHandler(
        token_endpoint="https://oidc.example.com/token", userinfo_endpoint="https://oidc.example.com/userinfo"
    )

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

    # Test 3: Other URLs are sent unchanged, even when they contain an endpoint's path
    mock_response.headers = {"DPoP-Nonce": "other-nonce"}
    jwks_headers = {"Authorization": f"Bearer {access_token}"}
    handler.request("GET", "https://oidc.example.com/token/jwks", headers=jwks_headers)
    mock_request.assert_called_with("GET", "https://oidc.example.com/token/jwks", headers=jwks_headers)
    assert handler.nonce == server_nonce


async def test_dpop_key_loaded_once(dpop_test_jwks):
    """Test that the private DPoP key is read once, not for every login."""
    first = DPoPHandler(
        token_endpoint="https://oidc.example.com/token", userinfo_endpoint="https://oidc.example.com/userinfo"
    )
    dpop_test_jwks.unlink()
    second = DPoPHandler(
        token_endpoint="https://oidc.example.com/token", userinfo_endpoint="https://oidc.example.com/userinfo"
    )

    assert second.private_key is first.private_key
    assert second.public_jwk == first.public_jwk


@pytest.mark.parametrize(
    ("provider_info", "missing"),
    [
        ({}, "token or userinfo"),
        ({"userinfo_endpoint": "https://oidc.example.com/userinfo"}, "token"),
        ({"token_endpoint": "https://oidc.example.com/token", "userinfo_endpoint": ""}, "userinfo"),
    ],
)
async def test_dpop_handler_requires_endpoints(dpop_test_jwks, provider_info, missing):
    """Test that a DPoP handler cannot be created without the endpoints it adds proofs to."""
    with pytest.raises(ValueError, match=f"OIDC provider has no {missing} endpoint for DPoP"):
        DPoPHandler.from_provider_info(provider_info)


async def test_dpop_handler_from_provider_info(dpop_test_jwks):
    """Test that a DPoP handler is created for the endpoints in the provider's metadata."""
    handler = DPoPHandler.from_provider_info(
        {"token_endpoint": "https://oidc.example.com/token", "userinfo_endpoint": "https://oidc.example.com/userinfo"}
    )

    assert handler.token_endpoint == "https://oidc.example.com/token"
    assert handler.userinfo_endpoint == "https://oidc.example.com/userinfo"


def _response(
    status_code: int, nonce: str | None = None, body: object = None, headers: dict[str, str] | None = None
) -> Response:
    response = Response()
    response.status_code = status_code
    if nonce:
        response.headers["DPoP-Nonce"] = nonce
    response.headers.update(headers or {})
    response._content = json.dumps(body or {}).encode()
    return response


async def test_dpop_request_nonce_retry(dpop_test_jwks, monkeypatch):
    """Test that a request rejected for want of the provider's nonce is sent once more with the nonce."""
    token_url = "https://oidc.example.com/token"
    userinfo_url = "https://oidc.example.com/userinfo"
    handler = DPoPHandler(token_endpoint=token_url, userinfo_endpoint=userinfo_url)
    mock_request = MagicMock(
        side_effect=[
            # Token endpoint: error in the body of a 400 response (RFC 9449 Section 8)
            _response(status.HTTP_400_BAD_REQUEST, "nonce-1", {"error": "use_dpop_nonce"}),
            _response(status.HTTP_200_OK, "nonce-1"),
            # Userinfo endpoint, with a nonce of its own: error in WWW-Authenticate of a 401 response (Section 9)
            _response(
                status.HTTP_401_UNAUTHORIZED, "nonce-2", headers={"WWW-Authenticate": 'DPoP error="use_dpop_nonce"'}
            ),
            _response(status.HTTP_200_OK),
        ]
    )
    monkeypatch.setattr("metadata_backend.services.auth_service.requests.request", mock_request)

    assert handler.request("POST", token_url, data={"code": "c"}, headers={}).status_code == status.HTTP_200_OK
    assert (
        handler.request("GET", userinfo_url, headers={"Authorization": "Bearer at"}).status_code == status.HTTP_200_OK
    )

    proofs = [
        pyjwt.decode(call.kwargs["headers"]["DPoP"], options={"verify_signature": False})
        for call in mock_request.call_args_list
    ]
    assert [p["htu"] for p in proofs] == [token_url, token_url, userinfo_url, userinfo_url]
    assert [p["nonce"] for p in proofs] == [None, "nonce-1", "nonce-1", "nonce-2"]
    # Both userinfo proofs, the retry's too, are bound to the access token
    ath = urlsafe_b64encode(hashlib.sha256(b"at").digest()).decode().rstrip("=")
    assert [p.get("ath") for p in proofs] == [None, None, ath, ath]
    assert [call.kwargs.get("data") for call in mock_request.call_args_list[:2]] == [{"code": "c"}] * 2
    assert mock_request.call_args.kwargs["headers"]["Authorization"] == "DPoP at"
    assert handler.nonce == "nonce-2"


async def test_dpop_request_no_retry(dpop_test_jwks, monkeypatch):
    """Test that other errors, and a nonce error with the nonce already sent, are not retried."""
    token_url = "https://oidc.example.com/token"
    handler = DPoPHandler(token_endpoint=token_url, userinfo_endpoint="https://oidc.example.com/userinfo")
    handler.nonce = "nonce-1"
    mock_request = MagicMock(
        side_effect=[
            _response(status.HTTP_400_BAD_REQUEST, "nonce-2", {"error": "invalid_grant"}),
            _response(status.HTTP_400_BAD_REQUEST, "nonce-2", {"error": "use_dpop_nonce"}),
        ]
    )
    monkeypatch.setattr("metadata_backend.services.auth_service.requests.request", mock_request)

    # The nonce of an error response is still kept for the next request
    assert handler.request("POST", token_url, headers={}).status_code == status.HTTP_400_BAD_REQUEST
    assert handler.nonce == "nonce-2"
    assert handler.request("POST", token_url, headers={}).status_code == status.HTTP_400_BAD_REQUEST
    assert mock_request.call_count == 2


@pytest.mark.parametrize(
    "provider_info",
    [
        {},
        {"userinfo_endpoint": "http://mock/oidc/userinfo"},
        {"token_endpoint": "http://mock/oidc/token"},
    ],
)
async def test_dpop_callback_without_endpoint(csc_client, dpop_test_jwks, monkeypatch, provider_info):
    """Test that a DPoP login fails, rather than going without proofs, if the provider lacks an endpoint."""
    monkeypatch.setenv("OIDC_DPOP", "true")
    handler = AuthServiceHandler()
    handler._rph = MagicMock()
    handler._rph.get_session_information.return_value = {"iss": "http://mock/oidc"}
    handler._login_started["state"] = 0  # A login in progress
    handler._rph.get_client_from_session_key.return_value.get_context.return_value.provider_info = provider_info

    with pytest.raises(HTTPException) as e:
        await handler.callback("state", "code")

    assert e.value.status_code == status.HTTP_401_UNAUTHORIZED
    handler._rph.finalize.assert_not_called()


# Private JWKS files that DPoPHandler cannot load
INVALID_JWKS = [
    None,  # No key file
    {"keys": [{"kty": "EC", "crv": "P-256", "x": "AAAA", "y": "AAAA", "d": "AAAA"}]},  # Not a valid EC key
    # A valid EC key, but not on P-256, so it cannot sign ES256 proofs
    {"keys": [json.loads(ECAlgorithm.to_jwk(ec.generate_private_key(ec.SECP384R1())))]},
]


def _use_jwks(tmp_path: Path, monkeypatch, jwks: dict | None) -> Path:
    """Point DPoPHandler at a key file holding the JWKS, or at a missing file if the JWKS is None.

    :returns: Path of the key file
    """
    key_file = tmp_path / "private_jwks.json"  # Not the dpop_test_jwks fixture's file
    if jwks is not None:
        key_file.write_text(json.dumps(jwks))
    monkeypatch.setattr(DPoPHandler, "PRIVATE_JWK_PATH", key_file)
    return key_file


@pytest.mark.parametrize("jwks", INVALID_JWKS)
async def test_dpop_key_failure_not_cached(dpop_test_jwks, tmp_path, monkeypatch, jwks):
    """Test that an invalid key fails every time until it is fixed, and the fixed key then loads without a restart."""
    valid_jwks = json.loads(dpop_test_jwks.read_text())
    key_file = _use_jwks(tmp_path, monkeypatch, jwks)
    endpoints = {
        "token_endpoint": "https://oidc.example.com/token",
        "userinfo_endpoint": "https://oidc.example.com/userinfo",
    }

    for _ in range(2):
        with pytest.raises(ValueError):
            DPoPHandler(**endpoints)

    key_file.write_text(json.dumps(valid_jwks))
    assert DPoPHandler(**endpoints).private_key is not None


@pytest.mark.parametrize("jwks", INVALID_JWKS)
async def test_dpop_callback_invalid_key(csc_client, tmp_path, monkeypatch, jwks):
    """Test that a DPoP login with an unreadable, invalid or non-P-256 key fails with 401."""
    monkeypatch.setenv("OIDC_DPOP", "true")
    _use_jwks(tmp_path, monkeypatch, jwks)
    handler = AuthServiceHandler()
    handler._rph = MagicMock()
    handler._rph.get_session_information.return_value = {"iss": "http://mock/oidc"}
    handler._login_started["state"] = 0  # A login in progress
    handler._rph.get_client_from_session_key.return_value.get_context.return_value.provider_info = {
        "token_endpoint": "http://mock/oidc/token",
        "userinfo_endpoint": "http://mock/oidc/userinfo",
    }

    with pytest.raises(HTTPException) as e:
        await handler.callback("state", "code")

    assert e.value.status_code == status.HTTP_401_UNAUTHORIZED
    handler._rph.finalize.assert_not_called()


def test_dpop_httpc(dpop_test_jwks, monkeypatch):
    """Test that idpyoidc's client sends its requests, and those for the provider's keys, through dpop_request."""
    monkeypatch.setenv("OIDC_URL", "http://mock/oidc")
    monkeypatch.setenv("OIDC_CLIENT_SECRET", "x" * 32)  # idpyoidc requires at least 16 characters
    monkeypatch.setenv("OIDC_DPOP", "true")
    client = AuthServiceHandler().rph.init_client("aai")

    assert client.httpc is dpop_request
    assert client.keyjar.httpc is dpop_request


async def test_dpop_request_outside_login(dpop_test_jwks, monkeypatch):
    """Test that idpyoidc requests outside an OIDC login are sent without DPoP headers."""
    mock_request = MagicMock()
    monkeypatch.setattr("metadata_backend.services.auth_service.requests.request", mock_request)

    dpop_request("POST", "https://oidc.example.com/token", headers={})

    mock_request.assert_called_once_with("POST", "https://oidc.example.com/token", headers={})


async def test_get_pouta_access_token_from_userinfo_success(pouta_handler, userinfo_requests):
    """Test that the Pouta userinfo request is sent with DPoP to the discovered endpoint, off the event loop."""
    request_threads: list[int] = []

    def send(*args, **kwargs) -> Response:
        request_threads.append(threading.get_ident())
        return _response(status.HTTP_200_OK, body={"pouta_access_token": "pouta-token"})

    mock_request = userinfo_requests()
    mock_request.side_effect = send

    assert await pouta_handler.get_pouta_access_token_from_userinfo("oidc-token") == "pouta-token"

    mock_request.assert_called_once()
    assert mock_request.call_args.args == ("GET", "http://mockauth:8005/userinfo")
    assert mock_request.call_args.kwargs["timeout"] == AuthServiceHandler.OIDC_REQUEST_TIMEOUT
    headers = mock_request.call_args.kwargs["headers"]
    assert headers["Authorization"] == "DPoP oidc-token"
    proof = pyjwt.decode(headers["DPoP"], options={"verify_signature": False})
    assert proof["ath"] == urlsafe_b64encode(hashlib.sha256(b"oidc-token").digest()).decode().rstrip("=")
    assert threading.get_ident() not in request_threads


async def test_get_pouta_access_token_from_userinfo_retries_with_nonce(pouta_handler, userinfo_requests):
    """Test that a userinfo request rejected for want of the provider's nonce is sent once more with it."""
    mock_request = userinfo_requests(
        _response(status.HTTP_401_UNAUTHORIZED, "nonce-1", headers={"WWW-Authenticate": 'DPoP error="use_dpop_nonce"'}),
        _response(status.HTTP_200_OK, body={"pouta_access_token": "pouta-token"}),
    )

    assert await pouta_handler.get_pouta_access_token_from_userinfo("oidc-token") == "pouta-token"

    proofs = [
        pyjwt.decode(call.kwargs["headers"]["DPoP"], options={"verify_signature": False})
        for call in mock_request.call_args_list
    ]
    assert [p["nonce"] for p in proofs] == [None, "nonce-1"]


async def test_get_pouta_access_token_from_userinfo_no_retry_without_nonce_error(pouta_handler, userinfo_requests):
    """Test that a 401 response is not retried, even with a DPoP-Nonce, unless its error is use_dpop_nonce."""
    mock_request = userinfo_requests(_response(status.HTTP_401_UNAUTHORIZED, "nonce-1"))

    with pytest.raises(HTTPException) as e:
        await pouta_handler.get_pouta_access_token_from_userinfo("oidc-token")
    assert e.value.status_code == status.HTTP_401_UNAUTHORIZED
    mock_request.assert_called_once()


async def test_get_pouta_access_token_from_userinfo_without_dpop(
    mock_oidc_url, userinfo_requests, tmp_path, monkeypatch
):
    """Test that without DPoP the Pouta userinfo request sends a Bearer token, and needs no DPoP key."""
    monkeypatch.setenv("OIDC_DPOP", "false")
    _use_jwks(tmp_path, monkeypatch, None)  # No key file
    handler = AuthServiceHandler()
    handler._provider_info = {"userinfo_endpoint": f"{mock_oidc_url}/userinfo"}
    mock_request = userinfo_requests(_response(status.HTTP_200_OK, body={"pouta_access_token": "pouta-token"}))

    assert await handler.get_pouta_access_token_from_userinfo("oidc-token") == "pouta-token"

    mock_request.assert_called_once_with(
        "GET",
        f"{mock_oidc_url}/userinfo",
        headers={"Authorization": "Bearer oidc-token"},
        timeout=AuthServiceHandler.OIDC_REQUEST_TIMEOUT,
    )


async def test_get_pouta_access_token_from_userinfo_missing_oidc_token(pouta_handler):
    """Test that missing OIDC access token raises HTTPException."""
    try:
        await pouta_handler.get_pouta_access_token_from_userinfo("")
    except HTTPException as ex:
        assert ex.status_code == status.HTTP_401_UNAUTHORIZED
        assert ex.detail == "Missing OIDC access token"
    else:
        raise AssertionError("Expected HTTPException")


async def test_get_pouta_access_token_from_userinfo_upstream_error(pouta_handler, userinfo_requests):
    """Test that a 500 response from the upstream server triggers a 401 HTTPException."""
    userinfo_requests(_response(status.HTTP_500_INTERNAL_SERVER_ERROR))

    try:
        await pouta_handler.get_pouta_access_token_from_userinfo("oidc-token")
    except HTTPException as ex:
        assert ex.status_code == status.HTTP_401_UNAUTHORIZED
    else:
        raise AssertionError("Expected HTTPException")


async def test_get_pouta_access_token_discovery_fetched_once(pouta_handler, userinfo_requests, monkeypatch):
    """Test that the userinfo endpoint is taken from the provider's discovery document, fetched once."""
    response = {"pouta_access_token": "pouta-token"}
    mock_request = userinfo_requests(
        _response(status.HTTP_200_OK, body=response), _response(status.HTTP_200_OK, body=response)
    )
    pouta_handler._provider_info = None
    userinfo_url = "http://mockauth:8005/idp/profile/oidc/userinfo"
    mock_discovery = AsyncMock(
        return_value={"token_endpoint": "http://mockauth:8005/token", "userinfo_endpoint": userinfo_url}
    )
    monkeypatch.setattr(pouta_handler, "_request", mock_discovery)

    assert await pouta_handler.get_pouta_access_token_from_userinfo("oidc-token") == "pouta-token"
    assert await pouta_handler.get_pouta_access_token_from_userinfo("oidc-token") == "pouta-token"

    mock_discovery.assert_awaited_once_with(url=URL(pouta_handler.oidc_url))
    assert [call.args[1] for call in mock_request.call_args_list] == [userinfo_url, userinfo_url]


@pytest.mark.parametrize(
    "discovery",
    [
        ServiceHandlerSystemException("auth"),  # The discovery request failed
        "<html>Service unavailable</html>",  # The discovery document is not JSON
    ],
)
async def test_get_pouta_access_token_discovery_failure(pouta_handler, userinfo_requests, monkeypatch, discovery):
    """Test that a failed discovery fails with 401, and is not kept, so the next call fetches it again."""
    mock_request = userinfo_requests(_response(status.HTTP_200_OK, body={"pouta_access_token": "pouta-token"}))
    pouta_handler._provider_info = None
    mock_discovery = AsyncMock(
        side_effect=[
            discovery,
            {"token_endpoint": "http://mockauth:8005/token", "userinfo_endpoint": "http://mockauth:8005/userinfo"},
        ]
    )
    monkeypatch.setattr(pouta_handler, "_request", mock_discovery)

    with pytest.raises(HTTPException) as e:
        await pouta_handler.get_pouta_access_token_from_userinfo("oidc-token")
    assert e.value.status_code == status.HTTP_401_UNAUTHORIZED
    mock_request.assert_not_called()

    assert await pouta_handler.get_pouta_access_token_from_userinfo("oidc-token") == "pouta-token"
    assert mock_discovery.await_count == 2


async def test_get_pouta_access_token_discovery_without_userinfo_endpoint(pouta_handler, userinfo_requests):
    """Test that a provider listing no userinfo endpoint fails with 401."""
    mock_request = userinfo_requests()
    pouta_handler._provider_info = {"token_endpoint": "http://mockauth:8005/token"}

    with pytest.raises(HTTPException) as e:
        await pouta_handler.get_pouta_access_token_from_userinfo("oidc-token")
    assert e.value.status_code == status.HTTP_401_UNAUTHORIZED
    mock_request.assert_not_called()


@pytest.mark.parametrize("jwks", INVALID_JWKS)
async def test_get_pouta_access_token_invalid_key(pouta_handler, userinfo_requests, tmp_path, monkeypatch, jwks):
    """Test that the Pouta userinfo request with an unreadable, invalid or non-P-256 key fails with 401."""
    mock_request = userinfo_requests()
    _use_jwks(tmp_path, monkeypatch, jwks)

    with pytest.raises(HTTPException) as e:
        await pouta_handler.get_pouta_access_token_from_userinfo("oidc-token")
    assert e.value.status_code == status.HTTP_401_UNAUTHORIZED
    mock_request.assert_not_called()


async def test_concurrent_dpop_callbacks(csc_client, dpop_test_jwks, monkeypatch):
    """Test that overlapping OIDC callbacks on one event loop each send their own DPoP proofs."""

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
    client = MagicMock()
    client.get_context.return_value.provider_info = {"token_endpoint": token_url, "userinfo_endpoint": userinfo_url}
    monkeypatch.setattr(rph, "get_client_from_session_key", lambda state: client)
    monkeypatch.setattr(rph, "finalize", finalize)
    monkeypatch.setattr(rph, "get_valid_access_token", lambda state: (f"token-{state}", 0))
    handler._login_started.update(dict.fromkeys(codes, 0))  # Logins in progress

    results = dict(
        zip(
            codes,
            await asyncio.gather(*(handler.callback(code, code) for code in codes), return_exceptions=True),
            strict=True,
        )
    )

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


async def test_concurrent_begin(mock_oidc_url, monkeypatch):
    """Test that logins arriving together set up the client once, off the event loop."""
    handler = AuthServiceHandler()
    setup_threads: list[int] = []

    def client_setup(issuer_id: str) -> MagicMock:
        setup_threads.append(threading.get_ident())
        time.sleep(0.05)  # Long enough for the other logins to arrive
        return MagicMock()

    monkeypatch.setattr(handler.rph, "client_setup", client_setup)
    monkeypatch.setattr(handler.rph, "init_authorization", lambda client: f"{mock_oidc_url}/authorize?state=s")

    await asyncio.gather(*(handler.begin_login() for _ in range(3)))

    assert len(setup_threads) == 1
    assert threading.get_ident() not in setup_threads


async def test_begin_setup_errors(mock_oidc_url, monkeypatch, caplog):
    """Test that a failed setup is retried by the next login, and that a login waits at most OIDC_SETUP_WAIT.

    A failed login is a 401 with no reason, so the reason is read from the error log.
    """
    monkeypatch.setattr(AuthServiceHandler, "OIDC_SETUP_WAIT", 0.05)
    handler = AuthServiceHandler()
    setup = MagicMock(side_effect=[OidcServiceError("discovery failed"), MagicMock()])
    monkeypatch.setattr(handler.rph, "client_setup", setup)
    monkeypatch.setattr(handler.rph, "init_authorization", lambda client: "http://mock/authorize?state=s")

    # While another login holds the lock to set up the client, a login gives up after OIDC_SETUP_WAIT.
    with handler._setup_lock:
        with pytest.raises(HTTPException) as e:
            await handler.begin_login()
    assert e.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert "TimeoutError('Timed out waiting for another login to set up the OIDC client')" in caplog.text
    setup.assert_not_called()

    # The setup fails, as if discovery failed. The failure is not kept, so the next login sets up the client.
    caplog.clear()
    with pytest.raises(HTTPException) as e:
        await handler.begin_login()
    assert e.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert "discovery failed" in caplog.text

    assert await handler.begin_login() == "http://mock/authorize?state=s"
    assert setup.call_count == 2


OIDC_ISSUER = "http://mock/oidc"


@pytest.fixture
def oidc_provider(dpop_test_jwks, monkeypatch) -> MagicMock:
    """A mock OIDC provider for the real RPHandler, whose requests all go through dpop_request.

    :returns: The mock of requests.request, whose `bodies` maps each path to its response body
    """
    monkeypatch.setenv("OIDC_URL", OIDC_ISSUER)
    monkeypatch.setenv("OIDC_CLIENT_SECRET", "x" * 32)  # idpyoidc requires at least 16 characters
    monkeypatch.setenv("OIDC_DPOP", "true")
    # The provider's ID tokens are unsigned. AuthServiceHandler then replaces idpyoidc's verification.
    monkeypatch.setenv("OIDC_VERIFY_ID_TOKEN", "false")
    monkeypatch.setattr(oidc, "verify_id_token", oidc.verify_id_token)
    # For the application JWT the callback creates
    monkeypatch.setenv("JWT_KEY", "a2tra2tra2tra2tra2tra2tra2tra2tra2tra2tra2s=")
    bodies = {
        "/.well-known/openid-configuration": {
            "issuer": OIDC_ISSUER,
            "authorization_endpoint": f"{OIDC_ISSUER}/authorize",
            "token_endpoint": f"{OIDC_ISSUER}/token",
            "userinfo_endpoint": f"{OIDC_ISSUER}/userinfo",
            "jwks_uri": f"{OIDC_ISSUER}/jwks",
            "response_types_supported": ["code"],
            "subject_types_supported": ["public"],
            "id_token_signing_alg_values_supported": ["RS256"],
        },
        "/jwks": {"keys": []},
        "/token": {
            "access_token": "access",
            "token_type": "DPoP",
            "expires_in": 60,
            "id_token": pyjwt.encode({"sub": "user"}, "x" * 32),
        },
        "/userinfo": {"sub": "user"},
    }

    def request(method: str, url: str, **kwargs) -> Response:
        response = Response()
        response.status_code = 200
        response.headers["Content-Type"] = "application/json"
        response._content = json.dumps(bodies[url.removeprefix(OIDC_ISSUER)]).encode()
        return response

    mock = MagicMock(side_effect=request)
    mock.bodies = bodies
    monkeypatch.setattr("metadata_backend.services.auth_service.requests.request", mock)
    return mock


async def test_login_lifecycle(oidc_provider, monkeypatch):
    """Test that logins share idpyoidc's client, and that each login's state is removed once it is used.

    Uses the real RPHandler.
    """
    monkeypatch.setattr(AuthServiceHandler, "OIDC_REQUEST_TIMEOUT", 7)  # Not cryptojwt's default of 10
    handler = AuthServiceHandler()
    first, second, third = [URL(await handler.begin_login()).query["state"] for _ in range(3)]

    # Only the first login set up the client
    assert [c.args[1] for c in oidc_provider.call_args_list] == [
        f"{OIDC_ISSUER}/.well-known/openid-configuration",
        f"{OIDC_ISSUER}/jwks",
    ]

    # The first login finishes after the others have begun, and its state is removed
    _, access_token, _ = await handler.callback(first, "code")
    assert access_token == "access"
    assert all(c.kwargs["timeout"] == 7 for c in oidc_provider.call_args_list)

    # The token and userinfo requests carry DPoP proofs, and userinfo the DPoP-bound access token
    sent = {c.args[1]: c.kwargs.get("headers") or {} for c in oidc_provider.call_args_list}
    assert sent.keys() >= {f"{OIDC_ISSUER}/token", f"{OIDC_ISSUER}/userinfo"}
    assert sent[f"{OIDC_ISSUER}/token"]["DPoP"]
    assert sent[f"{OIDC_ISSUER}/userinfo"]["DPoP"]
    assert sent[f"{OIDC_ISSUER}/userinfo"]["Authorization"] == "DPoP access"
    assert list(handler._login_started) == [second, third]

    # A used or unknown state fails, and removes nothing
    for state in (first, "unknown"):
        with pytest.raises(HTTPException) as e:
            await handler.callback(state, "code")
        assert e.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert list(handler._login_started) == [second, third]

    # Of two callbacks for one login, only the first finishes it. Its state is removed after it finishes.
    results = await asyncio.gather(
        handler.callback(second, "code"), handler.callback(second, "code"), return_exceptions=True
    )
    assert results[0][1] == "access"
    assert isinstance(results[1], HTTPException) and results[1].status_code == status.HTTP_401_UNAUTHORIZED
    assert list(handler._login_started) == [third]
    with pytest.raises(KeyError):
        handler.rph.get_session_information(second)

    # A failed login's state is removed too
    monkeypatch.setattr(handler.rph, "finalize", MagicMock(side_effect=OidcServiceError("token request failed")))
    with pytest.raises(HTTPException):
        await handler.callback(third, "code")
    assert handler._login_started == {}
    with pytest.raises(KeyError):
        handler.rph.get_session_information(third)


async def test_callback_expired_access_token(oidc_provider):
    """Test that a login fails with 401, not 500, if the provider returns an access token that has expired."""
    oidc_provider.bodies["/token"]["expires_in"] = 0
    handler = AuthServiceHandler()
    state = URL(await handler.begin_login()).query["state"]

    with pytest.raises(HTTPException) as e:
        await handler.callback(state, "code")

    assert e.value.status_code == status.HTTP_401_UNAUTHORIZED
    with pytest.raises(KeyError):
        handler.rph.get_session_information(state)


async def test_unfinished_logins_expire(oidc_provider, monkeypatch):
    """Test that a login removes the state of logins older than OIDC_LOGIN_TIMEOUT."""
    handler = AuthServiceHandler()
    first = URL(await handler.begin_login()).query["state"]

    monkeypatch.setattr(AuthServiceHandler, "OIDC_LOGIN_TIMEOUT", 0)
    second = URL(await handler.begin_login()).query["state"]

    with pytest.raises(KeyError):
        handler.rph.get_session_information(first)
    assert list(handler._login_started) == [second]
