"""Test verifying the signed token of the sync service account."""

from datetime import timedelta

import pytest
from starlette.requests import Request

from metadata_backend.api.dependencies import verify_sync
from metadata_backend.api.exceptions import UnauthorizedUserException
from tests.sync import (
    hmac_signed_sync_token,
    sign_sync_token,
    sync_claims,
    sync_clients,
    sync_key_pair,
)
from tests.unit.conftest import (
    TEST_SYNC_AUDIENCE,
    TEST_SYNC_ISSUER,
    TEST_SYNC_PRIVATE_KEY,
    TEST_SYNC_PUBLIC_KEY,
)

OTHER_AUDIENCE = "https://elsewhere.test/api/sync"
OTHER_ISSUER = "someone-else"


def __configure_sync_clients(monkeypatch, *clients: tuple[str, ...]) -> None:
    """Configure sync clients."""

    monkeypatch.setenv("SYNC_CLIENTS", sync_clients(*clients or ((TEST_SYNC_ISSUER, TEST_SYNC_PUBLIC_KEY),)))
    monkeypatch.setenv("SYNC_AUDIENCE", TEST_SYNC_AUDIENCE)


def _sync_request(authorization: str | None = None) -> Request:
    """A request with the sync authorization header."""

    # Header values are bytes, which Starlette decodes as latin-1.
    headers = [(b"authorization", authorization.encode("latin-1"))] if authorization is not None else []
    return Request({"type": "http", "headers": headers})


def _sync_token(audience: str = TEST_SYNC_AUDIENCE, issuer: str = TEST_SYNC_ISSUER, **claims) -> str:
    """A singled sync token."""

    return sign_sync_token(sync_claims(audience, issuer, **claims), TEST_SYNC_PRIVATE_KEY)


def test_verify_sync(monkeypatch):
    __configure_sync_clients(monkeypatch)

    verify_sync(_sync_request(f"Bearer {_sync_token()}"))


def test_verify_sync_multiple_keys(monkeypatch):
    private_key, public_key = sync_key_pair()
    __configure_sync_clients(monkeypatch, (TEST_SYNC_ISSUER, TEST_SYNC_PUBLIC_KEY, public_key))

    verify_sync(_sync_request(f"Bearer {_sync_token()}"))
    verify_sync(
        _sync_request(f"Bearer {sign_sync_token(sync_claims(TEST_SYNC_AUDIENCE, TEST_SYNC_ISSUER), private_key)}")
    )


def test_verify_sync_multiple_clients(monkeypatch):
    private_key, public_key = sync_key_pair()
    __configure_sync_clients(monkeypatch, (TEST_SYNC_ISSUER, TEST_SYNC_PUBLIC_KEY), (OTHER_ISSUER, public_key))

    verify_sync(_sync_request(f"Bearer {_sync_token()}"))
    verify_sync(_sync_request(f"Bearer {sign_sync_token(sync_claims(TEST_SYNC_AUDIENCE, OTHER_ISSUER), private_key)}"))


def test_verify_sync_multiple_clients_issuer(monkeypatch):
    """A client's key signs for that issuer only."""

    _, public_key = sync_key_pair()
    __configure_sync_clients(monkeypatch, (TEST_SYNC_ISSUER, TEST_SYNC_PUBLIC_KEY), (OTHER_ISSUER, public_key))

    # Signed by the first client's key, claiming to be the second one.
    token = sign_sync_token(sync_claims(TEST_SYNC_AUDIENCE, OTHER_ISSUER), TEST_SYNC_PRIVATE_KEY)

    with pytest.raises(UnauthorizedUserException):
        verify_sync(_sync_request(f"Bearer {token}"))


@pytest.mark.parametrize(
    "authorization",
    [
        None,
        "",
        "invalid",
        f"Basic {_sync_token()}",
        "Bearer",
        "Bearer \xe4",
        "Bearer not.a.token",
    ],
    ids=[
        "no header",
        "an empty header",
        "no scheme",
        "another scheme",
        "no token",
        "a non-ASCII token",
        "a token that is not a JWT",
    ],
)
def test_verify_sync_invalid_header(monkeypatch, authorization):
    __configure_sync_clients(monkeypatch)

    with pytest.raises(UnauthorizedUserException):
        verify_sync(_sync_request(authorization))


@pytest.mark.parametrize(
    "token",
    [
        lambda: sign_sync_token(sync_claims(TEST_SYNC_AUDIENCE, TEST_SYNC_ISSUER), sync_key_pair()[0]),
        lambda: _sync_token(audience=OTHER_AUDIENCE),
        lambda: _sync_token(issuer=OTHER_ISSUER),
        lambda: _sync_token(lifetime=timedelta(seconds=-60)),
        lambda: sign_sync_token(
            {
                claim: value
                for claim, value in sync_claims(TEST_SYNC_AUDIENCE, TEST_SYNC_ISSUER).items()
                if claim != "sub"
            },
            TEST_SYNC_PRIVATE_KEY,
        ),
        lambda: hmac_signed_sync_token(sync_claims(TEST_SYNC_AUDIENCE, TEST_SYNC_ISSUER), TEST_SYNC_PUBLIC_KEY),
    ],
    ids=[
        "signed by another key",
        "issued for another audience",
        "issued by another issuer",
        "expired",
        "missing a claim",
        "signed with the public key",
    ],
)
def test_verify_sync_invalid_token(monkeypatch, token):
    __configure_sync_clients(monkeypatch)

    with pytest.raises(UnauthorizedUserException):
        verify_sync(_sync_request(f"Bearer {token()}"))


def test_verify_sync_no_clients(monkeypatch):
    __configure_sync_clients(monkeypatch)
    monkeypatch.delenv("SYNC_CLIENTS")

    with pytest.raises(UnauthorizedUserException):
        verify_sync(_sync_request(f"Bearer {_sync_token()}"))
