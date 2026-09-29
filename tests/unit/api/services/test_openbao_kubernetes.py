"""Test authenticating to OpenBao with Kubernetes.

These run the real OpenBaoService, with respx mocking in for the OpenBao server.
The service makes its usual HTTP calls and respx answers them.
"""

import json
import time

import httpx
import pytest
import respx

from metadata_backend.api.exceptions import ServiceHandlerSystemException, SystemException
from metadata_backend.api.services import openbao as openbao_module
from metadata_backend.api.services.openbao import OpenBaoService
from metadata_backend.conf.openbao import OpenBaoConfig
from metadata_backend.helpers.logger import LOG

URL = "http://openbao:8200"
ROLE = "sd-submit"
KEY_NAME = "test-key"

LOGIN_ROUTE = f"{URL}/v1/auth/kubernetes/login"
KEY_ROUTE = f"{URL}/v1/transit/keys/{KEY_NAME}"

KEY = {"data": {"name": KEY_NAME, "latest_version": 1, "keys": {"1": 1758000000}}}

# The Kubernetes service account token the login presents.
SERVICE_ACCOUNT_TOKEN = "service-account-jwt"

# The OpenBao tokens a login returns, and the lease each one is good for.
OPENBAO_TOKEN = "openbao-token"
FIRST_OPENBAO_TOKEN = "first-openbao-token"
SECOND_OPENBAO_TOKEN = "second-openbao-token"
LEASE_SECONDS = 3600


@pytest.fixture
def service_account_token(monkeypatch, tmp_path):
    """Create and use a Kubernetes service account token."""

    path = tmp_path / "token"
    path.write_text(f"{SERVICE_ACCOUNT_TOKEN}\n", encoding="utf-8")
    monkeypatch.setattr(openbao_module, "_K8_SERVICE_ACCOUNT_TOKEN_PATH", path)
    return path


def _service(**overrides: str) -> OpenBaoService:
    fields = {"OPENBAO_URL": URL, "OPENBAO_KUBERNETES_ROLE": ROLE, "OPENBAO_OBJECT_KEY_NAME": KEY_NAME}
    return OpenBaoService(OpenBaoConfig(**(fields | overrides)))


def _login_response(token: str = OPENBAO_TOKEN, lease: int = LEASE_SECONDS) -> httpx.Response:
    return httpx.Response(200, json={"auth": {"client_token": token, "lease_duration": lease}})


@respx.mock
async def test_login(service_account_token) -> None:
    login = respx.post(LOGIN_ROUTE).mock(return_value=_login_response())
    key = respx.get(KEY_ROUTE).mock(return_value=httpx.Response(200, json=KEY))

    service = _service()
    await service._read_key()
    await service.close()

    assert login.call_count == 1
    # Login request has role and service account token.
    assert json.loads(login.calls[0].request.read()) == {"role": ROLE, "jwt": SERVICE_ACCOUNT_TOKEN}
    assert "X-Vault-Token" not in login.calls[0].request.headers
    # OpenBao token returned by login is used in the key request.
    assert key.calls[0].request.headers["X-Vault-Token"] == OPENBAO_TOKEN


@respx.mock
async def test_token_reused(service_account_token) -> None:
    login = respx.post(LOGIN_ROUTE).mock(return_value=_login_response(lease=LEASE_SECONDS))
    respx.get(KEY_ROUTE).mock(return_value=httpx.Response(200, json=KEY))

    service = _service()
    await service._read_key()
    await service._read_key()
    await service.close()

    assert login.call_count == 1


@respx.mock
async def test_token_replaced_before_expiry(service_account_token, monkeypatch) -> None:
    login = respx.post(LOGIN_ROUTE).mock(
        side_effect=[_login_response(FIRST_OPENBAO_TOKEN), _login_response(SECOND_OPENBAO_TOKEN)]
    )
    key = respx.get(KEY_ROUTE).mock(return_value=httpx.Response(200, json=KEY))

    service = _service()
    await service._read_key()

    # Expire token.
    monkeypatch.setattr(time, "monotonic", lambda: service._k8_login_until + 1)
    await service._read_key()
    await service.close()

    assert login.call_count == 2
    assert [call.request.headers["X-Vault-Token"] for call in key.calls] == [
        FIRST_OPENBAO_TOKEN,
        SECOND_OPENBAO_TOKEN,
    ]


@respx.mock
async def test_login_refused(service_account_token, caplog) -> None:
    respx.post(LOGIN_ROUTE).mock(return_value=httpx.Response(403, json={"errors": ["permission denied"]}))

    service = _service()

    with pytest.raises(ServiceHandlerSystemException):
        await service._read_key()

    await service.close()

    assert f"Failed to log in to OpenBao as '{ROLE}'" in caplog.text


@respx.mock
async def test_login_payload_not_logged(service_account_token, caplog) -> None:
    respx.post(LOGIN_ROUTE).mock(return_value=_login_response())
    respx.get(KEY_ROUTE).mock(return_value=httpx.Response(200, json=KEY))

    service = _service()
    with caplog.at_level("DEBUG", logger=LOG.name):
        await service._read_key()
    await service.close()

    assert SERVICE_ACCOUNT_TOKEN not in caplog.text


@respx.mock
async def test_refused_token_replaced(service_account_token) -> None:
    login = respx.post(LOGIN_ROUTE).mock(
        side_effect=[_login_response(FIRST_OPENBAO_TOKEN), _login_response(SECOND_OPENBAO_TOKEN)]
    )
    key = respx.get(KEY_ROUTE).mock(side_effect=[httpx.Response(403), httpx.Response(200, json=KEY)])

    service = _service()
    await service._read_key()
    await service.close()

    assert login.call_count == 2
    assert [call.request.headers["X-Vault-Token"] for call in key.calls] == [
        FIRST_OPENBAO_TOKEN,
        SECOND_OPENBAO_TOKEN,
    ]


@respx.mock
async def test_refused_token_logs_in_only_once(service_account_token, caplog) -> None:
    login = respx.post(LOGIN_ROUTE).mock(return_value=_login_response())
    key = respx.get(KEY_ROUTE).mock(return_value=httpx.Response(403))

    service = _service()

    with pytest.raises(ServiceHandlerSystemException):
        await service._read_key()

    await service.close()

    assert login.call_count == 2
    assert key.call_count == 2
    assert f"Failed to read the OpenBao key encryption key '{KEY_NAME}'." in caplog.text


@respx.mock
async def test_server_error_retried(service_account_token, monkeypatch) -> None:
    monkeypatch.setattr("metadata_backend.services.service_handler.RETRY_DELAY", 0)
    respx.post(LOGIN_ROUTE).mock(return_value=_login_response())
    key = respx.get(KEY_ROUTE).mock(side_effect=[httpx.Response(503), httpx.Response(200, json=KEY)])

    service = _service()
    assert await service._read_key() == KEY["data"]
    await service.close()

    assert key.call_count == 2


async def test_no_service_account_token(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(openbao_module, "_K8_SERVICE_ACCOUNT_TOKEN_PATH", tmp_path / "absent")

    service = _service()

    with pytest.raises(SystemException, match="Failed to read the Kubernetes service account token"):
        await service._read_key()

    await service.close()
