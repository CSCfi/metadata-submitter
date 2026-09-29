"""Test encrypting and decrypting metadata objects with OpenBao."""

import pytest

from metadata_backend.api.exceptions import SystemException
from metadata_backend.api.services.openbao import (
    _MAX_DATA_KEY_LENGTH,
    _MAX_KEY_NAME_LENGTH,
    SD_SUBMIT_MAGIC,
    OpenBaoService,
    _is_asymmetric,
    _write_envelope,
    is_encrypted,
)
from metadata_backend.conf.openbao import DIRECT, ENVELOPE, ObjectEncryption, OpenBaoConfig
from tests.unit.openbao import MockOpenBaoService

DOCUMENT = '<TEST alias="1"><VALUE>test</VALUE></TEST>'


def _openbao(encryption: ObjectEncryption) -> MockOpenBaoService:
    return MockOpenBaoService(encryption, asymmetric=encryption != DIRECT)


def _object(kind: int, body: bytes = b"", key_name: bytes = b"key") -> bytes:
    """Returns an expected stored metadata object."""

    return SD_SUBMIT_MAGIC + bytes([kind, len(key_name)]) + key_name + body


@pytest.mark.parametrize("encryption", [ENVELOPE, DIRECT])
async def test_encrypt_and_decrypt(encryption: ObjectEncryption) -> None:
    openbao = _openbao(encryption)

    data = await openbao.encrypt(DOCUMENT)

    assert is_encrypted(data)
    assert data.startswith(SD_SUBMIT_MAGIC)
    assert DOCUMENT.encode("utf-8") not in data
    assert await openbao.decrypt(data) == DOCUMENT


@pytest.mark.parametrize("asymmetric", [True, False])
async def test_envelope_encryption_asymmetric_and_symmetric(asymmetric: bool) -> None:
    openbao = MockOpenBaoService(ENVELOPE, asymmetric=asymmetric)

    assert await openbao.decrypt(await openbao.encrypt(DOCUMENT)) == DOCUMENT


@pytest.mark.parametrize("encryption", [ENVELOPE, DIRECT])
async def test_change_encryption_method(encryption: ObjectEncryption) -> None:
    decryption = DIRECT if encryption == ENVELOPE else ENVELOPE

    written = await MockOpenBaoService(encryption, asymmetric=False).encrypt(DOCUMENT)

    # Metadata objects are decrypted using the old method.
    assert await MockOpenBaoService(decryption, asymmetric=False).decrypt(written) == DOCUMENT


@pytest.mark.parametrize("encryption", [ENVELOPE, DIRECT])
async def test_change_encryption_key(encryption: ObjectEncryption) -> None:

    written = await MockOpenBaoService(encryption, asymmetric=False, key_name="old-key").encrypt(DOCUMENT)
    assert b"old-key" in written

    openbao = MockOpenBaoService(encryption, asymmetric=False, key_name="new-key")

    # Metadata objects are decrypted using the old key.
    assert await openbao.decrypt(written) == DOCUMENT
    assert openbao.key_names == ["old-key"]


def test_data_key_too_long() -> None:
    with pytest.raises(SystemException, match="a stored metadata object can hold"):
        _write_envelope("x" * (_MAX_DATA_KEY_LENGTH + 1), b"x" * 28)


def test_key_no_versions() -> None:
    with pytest.raises(SystemException, match="no key versions"):
        _is_asymmetric({"name": "test-key", "keys": None})


async def test_decrypt_unencrypted_object() -> None:
    with pytest.raises(SystemException, match="not encrypted with OpenBao"):
        await _openbao(ENVELOPE).decrypt(DOCUMENT.encode("utf-8"))


@pytest.mark.parametrize(
    "data",
    [
        # A encryption key name that is not ASCII.
        _object(1, b"x" * 40, key_name=b"\xff\xfe\xfd"),
        # Encrypted data encryption key that is not ASCII.
        _object(1, (4).to_bytes(2, "big") + b"\xff\xfe\xfd\xfc" + b"x" * 40),
    ],
)
async def test_decrypt_malformed_object(data: bytes) -> None:
    with pytest.raises(SystemException, match="malformed"):
        await _openbao(ENVELOPE).decrypt(data)


@pytest.mark.parametrize(
    "data",
    [
        # The magic alone, with no kind and no key_name_length after it.
        SD_SUBMIT_MAGIC,
        # The magic and the kind, with no key_name_length after them.
        SD_SUBMIT_MAGIC + bytes([1]),
        # A key name length of 8, but too short key.
        SD_SUBMIT_MAGIC + bytes([1, 8]) + b"short",
        # Envelope encrypted object with no data encryption key or body.
        _object(1),
        # Envelope encrypted object with data encryption key length of 500, but too short key.
        _object(1, (500).to_bytes(2, "big") + b"short"),
        # Envelope encrypted object with data encryption key only.
        _object(1, (4).to_bytes(2, "big") + b"key!"),
    ],
)
async def test_decrypt_truncated_object(data: bytes) -> None:
    with pytest.raises(SystemException, match="truncated"):
        await _openbao(ENVELOPE).decrypt(data)


async def test_decrypt_unknown_encryption() -> None:
    with pytest.raises(SystemException, match="unknown"):
        await _openbao(ENVELOPE).decrypt(_object(99, b"body"))


def _set_openbao_env(**overrides: str) -> OpenBaoConfig:
    fields = {
        "OPENBAO_URL": "http://openbao:8200",
        "OPENBAO_TOKEN": "test-token",
        "OPENBAO_OBJECT_KEY_NAME": "test-key",
    }
    return OpenBaoConfig(**(fields | overrides))


def test_missing_url() -> None:
    with pytest.raises(SystemException, match="are required to encrypt metadata objects"):
        OpenBaoService(_set_openbao_env(OPENBAO_URL=""))


@pytest.mark.parametrize("key_name", ["kärlek", "x" * (_MAX_KEY_NAME_LENGTH + 1)])
def test_invalid_key_name(key_name: str) -> None:
    with pytest.raises(SystemException, match="ASCII characters"):
        OpenBaoService(_set_openbao_env(OPENBAO_OBJECT_KEY_NAME=key_name))


@pytest.mark.parametrize("asymmetric", [True, False])
async def test_validate_envelope(asymmetric: bool) -> None:
    await MockOpenBaoService(ENVELOPE, asymmetric=asymmetric).validate()


async def test_validate_direct() -> None:
    await MockOpenBaoService(DIRECT, asymmetric=False).validate()

    with pytest.raises(SystemException, match="requires a symmetric OPENBAO_OBJECT_KEY_NAME"):
        await MockOpenBaoService(DIRECT, asymmetric=True).validate()
