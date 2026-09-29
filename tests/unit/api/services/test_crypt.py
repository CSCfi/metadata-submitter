"""Test reading the Crypt4GH keys, and retrieving the one a service publishes."""

import base64
import json
import textwrap
from typing import Callable, NamedTuple

import httpx
import pytest
import respx
from pydantic import ValidationError

from metadata_backend.api.exceptions import SystemException
from metadata_backend.api.services import crypt
from metadata_backend.api.services.bigpicture import read_bp_public_key
from metadata_backend.api.services.crypt import (
    C4GH_KEY_LENGTH,
    Crypt4GHPublicKeyProvider,
    Crypt4GHPublicKeyReader,
    parse_private_key,
    parse_public_key,
    public_key_of,
)
from tests.utils import generate_crypt4gh_keypair_env_values

_PASSPHRASE = "test-passphrase"
_PUBLIC_KEY_URL = "https://login.test/info"


@pytest.fixture(params=[_PASSPHRASE, None])
def keypair(request, tmp_path) -> tuple[str, str, str | None]:
    """A generated Crypt4GH keypair and its passphrase, one with a passphrase and one without."""

    private_key, public_key = generate_crypt4gh_keypair_env_values(tmp_path, request.param)
    return private_key, public_key, request.param


def test_parse_key(keypair) -> None:
    private_key, public_key, passphrase = keypair

    assert len(parse_private_key(private_key, passphrase)) == C4GH_KEY_LENGTH
    assert len(parse_public_key(public_key)) == C4GH_KEY_LENGTH


def test_parse_key_with_whitespace(keypair) -> None:
    """`base64 file` wraps the key at 76 characters and ends it with a newline."""

    _, public_key, _ = keypair
    wrapped = "\n".join(textwrap.wrap(public_key, 76)) + "\n"

    assert parse_public_key(wrapped) == parse_public_key(public_key)


@pytest.mark.parametrize("parse_key", [parse_public_key, parse_private_key])
def test_parse_key_not_pem(parse_key) -> None:
    key = base64.b64encode(b"not a PEM document").decode("utf-8")

    with pytest.raises(ValueError, match="not a PEM document"):
        parse_key(key)


def test_public_key_of(keypair) -> None:
    private_key, public_key, passphrase = keypair

    assert public_key_of(parse_private_key(private_key, passphrase)) == parse_public_key(public_key)


def test_parse_private_key_wrong_passphrase(tmp_path) -> None:
    private_key, _ = generate_crypt4gh_keypair_env_values(tmp_path, _PASSPHRASE)

    with pytest.raises(ValueError, match="could not be unlocked with the given passphrase"):
        parse_private_key(private_key, "wrong-passphrase")


def test_parse_private_key_missing_passphrase(tmp_path) -> None:
    private_key, _ = generate_crypt4gh_keypair_env_values(tmp_path, _PASSPHRASE)

    with pytest.raises(ValueError, match="no passphrase was given"):
        parse_private_key(private_key)


class _Deployment(NamedTuple):
    public_key_response: Callable[[str], httpx.Response]
    public_key_reader: Crypt4GHPublicKeyReader


def _sda_public_key_response(public_key: str) -> httpx.Response:
    """SDA /info public key response."""

    return httpx.Response(200, text=json.dumps({"public_key": public_key}))


def _other_public_key_response(public_key: str) -> httpx.Response:
    """Other public key response."""

    return httpx.Response(200, text=json.dumps({"keys": [{"c4gh": public_key}]}))


# Every deployment that retrieves its public key, tested against its response.
_DEPLOYMENTS = [
    pytest.param(_Deployment(_sda_public_key_response, read_bp_public_key), id="bigpicture"),
    pytest.param(
        _Deployment(_other_public_key_response, lambda response: response.json()["keys"][0]["c4gh"]), id="other"
    ),
]

# Possible failures when retrieving a public key.
_FAILURES = [
    pytest.param(lambda deployment: httpx.ConnectError("unreachable"), id="unreachable"),
    pytest.param(lambda deployment: httpx.Response(500), id="server_error"),
    pytest.param(lambda deployment: httpx.Response(200, text="<html>not the service</html>"), id="not_json"),
    pytest.param(lambda deployment: httpx.Response(200, text=json.dumps({})), id="no_key"),
    pytest.param(lambda deployment: deployment.public_key_response("not a key"), id="unreadable"),
]


@pytest.fixture(params=_DEPLOYMENTS)
def deployment(request) -> _Deployment:
    return request.param


@pytest.fixture(autouse=True)
def unset_crypt4gh_public_key(monkeypatch) -> None:
    monkeypatch.delenv("CRYPT4GH_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("CRYPT4GH_PUBLIC_KEY_URL", raising=False)


@pytest.fixture
def set_crypt4gh_public_key_url(monkeypatch) -> str:
    monkeypatch.setenv("CRYPT4GH_PUBLIC_KEY_URL", _PUBLIC_KEY_URL)
    return _PUBLIC_KEY_URL


@pytest.fixture
def public_key(tmp_path) -> str:
    _, public_key = generate_crypt4gh_keypair_env_values(tmp_path, _PASSPHRASE)
    return public_key


def _mock_public_key_route(served: httpx.Response | Exception) -> respx.Route:
    route = respx.get(_PUBLIC_KEY_URL)
    if isinstance(served, httpx.Response):
        return route.mock(return_value=served)
    return route.mock(side_effect=served)


def _public_key_provider(reader: Crypt4GHPublicKeyReader) -> Crypt4GHPublicKeyProvider:
    return Crypt4GHPublicKeyProvider(reader)


async def test_provider_configured_key(monkeypatch, deployment, public_key) -> None:
    monkeypatch.setenv("CRYPT4GH_PUBLIC_KEY", public_key)

    assert await _public_key_provider(deployment.public_key_reader).get() == parse_public_key(public_key)


def test_provider_no_key(deployment) -> None:
    with pytest.raises(ValidationError, match="CRYPT4GH_PUBLIC_KEY_URL or CRYPT4GH_PUBLIC_KEY is required"):
        _public_key_provider(deployment.public_key_reader)


@respx.mock
async def test_provider_retrieved_key_is_cached_until_it_expires(
    monkeypatch, deployment, set_crypt4gh_public_key_url, public_key, tmp_path
) -> None:
    """The retrieved key is used until it expires, and a rotated key retrieved once it has."""

    route = _mock_public_key_route(deployment.public_key_response(public_key))

    provider = _public_key_provider(deployment.public_key_reader)
    assert await provider.get() == parse_public_key(public_key)

    # The service rotates its key while the cached one is still in effect.
    _, rotated_key = generate_crypt4gh_keypair_env_values(tmp_path / "rotated", _PASSPHRASE)
    _mock_public_key_route(deployment.public_key_response(rotated_key))

    # The cached key is used, the rotated one not retrieved.
    assert await provider.get() == parse_public_key(public_key)
    assert route.call_count == 1

    # The cached key expires.
    monkeypatch.setattr(crypt, "_C4GH_KEY_CACHE_SECONDS", 0)

    # The rotated key is retrieved.
    assert await provider.get() == parse_public_key(rotated_key)
    assert route.call_count == 2


@respx.mock
async def test_provider_retrieved_key_is_preferred(
    monkeypatch, deployment, set_crypt4gh_public_key_url, public_key, tmp_path
) -> None:
    """Configure CRYPT4GH_PUBLIC_KEY (static_key) in addition to CRYPT4GH_PUBLIC_KEY_URL (public_key)."""
    _, static_key = generate_crypt4gh_keypair_env_values(tmp_path / "static", _PASSPHRASE)
    monkeypatch.setenv("CRYPT4GH_PUBLIC_KEY", static_key)
    _mock_public_key_route(deployment.public_key_response(public_key))

    assert await _public_key_provider(deployment.public_key_reader).get() == parse_public_key(public_key)


@respx.mock
@pytest.mark.parametrize("failure", _FAILURES)
async def test_provider_failure_without_cached_key(deployment, set_crypt4gh_public_key_url, failure) -> None:
    _mock_public_key_route(failure(deployment))

    with pytest.raises(SystemException, match="Failed to read the Crypt4GH public key"):
        await _public_key_provider(deployment.public_key_reader).get()


@respx.mock
@pytest.mark.parametrize("failure", _FAILURES)
async def test_provider_failure_with_cached_key(
    monkeypatch, deployment, set_crypt4gh_public_key_url, public_key, failure
) -> None:
    _mock_public_key_route(deployment.public_key_response(public_key))

    provider = _public_key_provider(deployment.public_key_reader)
    assert await provider.get() == parse_public_key(public_key)

    # The cached key expires, and the service no longer serves a usable one.
    monkeypatch.setattr(crypt, "_C4GH_KEY_CACHE_SECONDS", 0)
    _mock_public_key_route(failure(deployment))

    assert await provider.get() == parse_public_key(public_key)
