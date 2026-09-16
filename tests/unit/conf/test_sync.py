"""Test the sync service account configuration."""

import pytest
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from metadata_backend.conf.sync import SyncClient
from tests.sync import base64_public_keys, sync_key_pair


def _public_key(key) -> str:
    """The PEM public key of a generated private key."""

    return key.public_key().public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo).decode("utf-8")


def _sync_client(public_key: str) -> SyncClient:
    """A sync client configured with one public key."""

    return SyncClient(iss="sync-client", public_keys=[base64_public_keys(public_key)])


def test_sync_client_public_key():
    _, public_key = sync_key_pair()

    assert _sync_client(public_key).public_keys == [public_key]


def test_sync_client_public_key_of_another_kind():
    public_key = _public_key(rsa.generate_private_key(public_exponent=65537, key_size=2048))

    with pytest.raises(ValueError, match="P-256"):
        _sync_client(public_key)


def test_sync_client_public_key_of_another_curve():
    public_key = _public_key(ec.generate_private_key(ec.SECP384R1()))

    with pytest.raises(ValueError, match="P-256"):
        _sync_client(public_key)


def test_sync_client_public_key_not_pem():
    with pytest.raises(ValueError, match="PEM"):
        _sync_client("not a key")
