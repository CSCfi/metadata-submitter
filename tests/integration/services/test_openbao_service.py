"""Integration tests for encrypting metadata objects with OpenBao."""

import base64
import time
from typing import AsyncGenerator, Callable

import jwt
import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from metadata_backend.api.exceptions import ServiceHandlerSystemException, SystemException
from metadata_backend.api.models.health import Health
from metadata_backend.api.services import openbao as openbao_service
from metadata_backend.api.services.openbao import (
    _DATA_KEY_BITS,
    SD_SUBMIT_MAGIC,
    OpenBaoService,
    _decrypt_document,
    _encrypt_document,
    is_encrypted,
)
from metadata_backend.conf.openbao import DIRECT, ENVELOPE, ObjectEncryption, OpenBaoConfig
from tests.integration.conf import (
    openbao_kubernetes_namespace,
    openbao_kubernetes_role,
    openbao_kubernetes_service_account,
    openbao_object_key_name_asymmetric,
    openbao_object_key_name_symmetric,
    openbao_token,
    openbao_url,
)

# Large enough that no asymmetric key could encrypt it in one operation.
DOCUMENT = '<IMAGE alias="1"><TITLE>A whole slide image</TITLE></IMAGE>' * 1000

# What an rsa-4096 key encrypts in one RSA-OAEP with SHA-256 operation:
# 512 bytes of modulus less two 32 byte hashes and two bytes of padding.
RSA_4096_MAX_PLAINTEXT = 446

OpenBaoFactory = Callable[[ObjectEncryption, str], OpenBaoService]


@pytest.fixture
async def openbao() -> AsyncGenerator[OpenBaoFactory]:
    """Build OpenBao services against the test container, and close them afterwards."""

    services: list[OpenBaoService] = []

    def _create(encryption: ObjectEncryption, key_name: str) -> OpenBaoService:
        service = OpenBaoService(
            OpenBaoConfig(
                OPENBAO_URL=openbao_url,
                OPENBAO_TOKEN=openbao_token,
                OPENBAO_OBJECT_KEY_NAME=key_name,
                OPENBAO_OBJECT_ENCRYPTION=encryption,
            )
        )
        services.append(service)
        return service

    yield _create

    for service in services:
        await service.close()


async def read_public_key(service: OpenBaoService) -> tuple[rsa.RSAPublicKey, int]:
    """Read the public half of the service's key, with the version it belongs to."""

    key = await service._read_key()
    version = int(key["latest_version"])
    public_key = serialization.load_pem_public_key(key["keys"][str(version)]["public_key"].encode("utf-8"))
    assert isinstance(public_key, rsa.RSAPublicKey)
    return public_key, version


def encrypt_with_public_key(public_key: rsa.RSAPublicKey, version: int, data_key: bytes) -> str:
    encrypted = public_key.encrypt(
        data_key, padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
    )
    return f"vault:v{version}:{base64.b64encode(encrypted).decode('ascii')}"


# Test OpenBao encryption and decryption methods.
#


async def test_openbao_generates_the_data_key(openbao: OpenBaoFactory) -> None:
    key_name = openbao_object_key_name_asymmetric
    service = openbao(ENVELOPE, key_name)

    data = await service._transit(key_name, "transit/datakey/plaintext", {"bits": _DATA_KEY_BITS})
    data_key = base64.b64decode(data["plaintext"])
    encrypted_data_key = str(data["ciphertext"])

    assert len(data_key) == _DATA_KEY_BITS // 8
    assert encrypted_data_key.startswith("vault:v1:")

    ciphertext = _encrypt_document(data_key, DOCUMENT)
    del data_key

    data_key = await service._transit_decrypt(key_name, encrypted_data_key)
    assert _decrypt_document(data_key, ciphertext) == DOCUMENT


async def test_service_generates_the_data_key(openbao: OpenBaoFactory) -> None:
    key_name = openbao_object_key_name_asymmetric
    service = openbao(ENVELOPE, key_name)

    data_key = AESGCM.generate_key(bit_length=_DATA_KEY_BITS)
    ciphertext = _encrypt_document(data_key, DOCUMENT)

    encrypted_data_key = await service._transit_encrypt(data_key)
    assert encrypted_data_key.startswith("vault:v1:")

    assert await service._transit_decrypt(key_name, encrypted_data_key) == data_key
    assert _decrypt_document(data_key, ciphertext) == DOCUMENT


async def test_public_key_encrypts_the_data_key(openbao: OpenBaoFactory) -> None:
    key_name = openbao_object_key_name_asymmetric
    service = openbao(ENVELOPE, key_name)

    # Read once for the deployment rather than once per document.
    public_key, version = await read_public_key(service)

    data_key = AESGCM.generate_key(bit_length=_DATA_KEY_BITS)
    ciphertext = _encrypt_document(data_key, DOCUMENT)
    encrypted_data_key = encrypt_with_public_key(public_key, version, data_key)

    # Encrypting the document and its data encryption key reached nothing.
    assert await service._transit_decrypt(key_name, encrypted_data_key) == data_key
    assert _decrypt_document(data_key, ciphertext) == DOCUMENT


async def test_openbao_encrypts_the_document(openbao: OpenBaoFactory) -> None:
    key_name = openbao_object_key_name_symmetric
    service = openbao(DIRECT, key_name)

    ciphertext = await service._transit_encrypt(DOCUMENT.encode("utf-8"))
    assert ciphertext.startswith("vault:v1:")

    document = await service._transit_decrypt(key_name, ciphertext)
    assert document.decode("utf-8") == DOCUMENT


async def test_asymmetric_key_caps_plaintext(openbao: OpenBaoFactory) -> None:
    key_name = openbao_object_key_name_asymmetric
    service = openbao(ENVELOPE, key_name)

    plaintext = b"x" * RSA_4096_MAX_PLAINTEXT
    ciphertext = await service._transit_encrypt(plaintext)
    assert await service._transit_decrypt(key_name, ciphertext) == plaintext

    with pytest.raises(ServiceHandlerSystemException) as ex:
        await service._transit_encrypt(plaintext + b"x")
    assert ex.value.service_status_code == 500


# Test OpenBao service.
#


async def test_health(openbao: OpenBaoFactory) -> None:
    assert await openbao(ENVELOPE, openbao_object_key_name_asymmetric).get_health() == Health.UP


@pytest.mark.parametrize(
    "encryption, key_name",
    [
        (ENVELOPE, openbao_object_key_name_asymmetric),
        (ENVELOPE, openbao_object_key_name_symmetric),
        (DIRECT, openbao_object_key_name_symmetric),
    ],
)
async def test_encrypt_and_decrypt(openbao: OpenBaoFactory, encryption: ObjectEncryption, key_name: str) -> None:
    service = openbao(encryption, key_name)
    await service.validate()

    data = await service.encrypt(DOCUMENT)

    assert is_encrypted(data)
    assert data.startswith(SD_SUBMIT_MAGIC)
    assert DOCUMENT.encode("utf-8") not in data
    assert await service.decrypt(data) == DOCUMENT


async def test_decrypt_uses_the_key_the_object_names(openbao: OpenBaoFactory) -> None:
    written = await openbao(ENVELOPE, openbao_object_key_name_asymmetric).encrypt(DOCUMENT)
    assert openbao_object_key_name_asymmetric.encode("ascii") in written

    assert await openbao(ENVELOPE, openbao_object_key_name_symmetric).decrypt(written) == DOCUMENT


async def test_direct_refuses_an_asymmetric_key(openbao: OpenBaoFactory) -> None:
    service = openbao(DIRECT, openbao_object_key_name_asymmetric)

    with pytest.raises(SystemException, match="requires a symmetric OPENBAO_OBJECT_KEY_NAME"):
        await service.validate()

    with pytest.raises(ServiceHandlerSystemException):
        await service.encrypt(DOCUMENT)


# Test Kubernetes service account authentication.
#


def _service_account_token() -> str:
    """Create Kubernetes service account token."""

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_key = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ).decode("utf-8")

    issuer = "https://kubernetes.default.svc.cluster.local"
    now = int(time.time())
    claims = {
        "aud": [issuer],
        "iss": issuer,
        "iat": now,
        "nbf": now,
        "exp": now + 3600,
        "sub": f"system:serviceaccount:{openbao_kubernetes_namespace}:{openbao_kubernetes_service_account}",
        "kubernetes.io": {
            "namespace": openbao_kubernetes_namespace,
            "pod": {"name": "sd-submit-0", "uid": "aaaaaaaa-0000-0000-0000-000000000001"},
            "serviceaccount": {
                "name": openbao_kubernetes_service_account,
                "uid": "bbbbbbbb-0000-0000-0000-000000000002",
            },
        },
    }
    return jwt.encode(claims, private_key, algorithm="RS256")


@pytest.fixture
def service_account_token(monkeypatch, tmp_path):
    """Configure OpenBaoService to use a created Kubernetes service account token."""

    monkeypatch.delenv("OPENBAO_TOKEN", raising=False)

    path = tmp_path / "token"
    path.write_text(_service_account_token(), encoding="utf-8")
    monkeypatch.setattr(openbao_service, "_K8_SERVICE_ACCOUNT_TOKEN_PATH", path)


async def test_kubernetes_service_account(service_account_token) -> None:

    service = OpenBaoService(
        OpenBaoConfig(
            OPENBAO_URL=openbao_url,
            OPENBAO_KUBERNETES_ROLE=openbao_kubernetes_role,
            OPENBAO_OBJECT_KEY_NAME=openbao_object_key_name_asymmetric,
            OPENBAO_OBJECT_ENCRYPTION=ENVELOPE,
        )
    )

    try:
        await service.validate()
        assert await service.decrypt(await service.encrypt(DOCUMENT)) == DOCUMENT
        assert service._k8_login_token is not None
    finally:
        await service.close()
