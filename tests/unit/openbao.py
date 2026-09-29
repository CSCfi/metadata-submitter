"""An OpenBao mock service.

Everything except the HTTP calls is a real implementation.
"""

import base64
import functools
import os
from typing import Any

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from metadata_backend.api.models.health import Health
from metadata_backend.api.services.openbao import _NONCE_LENGTH, OpenBaoService
from metadata_backend.conf.openbao import ENVELOPE, ObjectEncryption, OpenBaoConfig

KEY_NAME = "test-key"


@functools.lru_cache(maxsize=1)
def _symmetric_key() -> bytes:
    """A symmetric key encryption key, generated once."""

    return AESGCM.generate_key(bit_length=256)


@functools.lru_cache(maxsize=1)
def _key_pair() -> rsa.RSAPrivateKey:
    """An asymmetric key encryption key, generated once."""

    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


class MockOpenBaoService(OpenBaoService):
    """An OpenBaoService whose key operations happen in memory."""

    def __init__(
        self,
        encryption: ObjectEncryption = ENVELOPE,
        *,
        asymmetric: bool = True,
        key_name: str = KEY_NAME,
    ) -> None:
        """
        Initialise the mock OpenBao service.

        :param encryption: How metadata objects are encrypted.
        :param asymmetric: Whether the key encryption key is asymmetric.
        :param key_name: The name of the encryption key.
        """

        super().__init__(
            OpenBaoConfig(
                OPENBAO_URL="http://openbao:8200",
                OPENBAO_TOKEN="test-token",
                OPENBAO_OBJECT_KEY_NAME=key_name,
                OPENBAO_OBJECT_ENCRYPTION=encryption,
            )
        )

        self.asymmetric = asymmetric
        # The key names the service asked for.
        self.key_names: list[str] = []

    async def get_health(self) -> Health:
        return Health.UP

    async def close(self) -> None:
        pass

    async def _read_key(self) -> dict[str, Any]:
        if not self.asymmetric:
            return {"name": self._key_name, "latest_version": 1, "keys": {"1": 1758000000}}

        public_key = (
            _key_pair()
            .public_key()
            .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
            .decode("utf-8")
        )
        return {"name": self._key_name, "latest_version": 1, "keys": {"1": {"public_key": public_key}}}

    async def _transit(self, key_name: str, path: str, json: dict[str, Any]) -> dict[str, Any]:
        self.key_names.append(key_name)

        if path == "transit/datakey/plaintext":
            data_key = AESGCM.generate_key(bit_length=json["bits"])
            return {
                "plaintext": base64.b64encode(data_key).decode("ascii"),
                "ciphertext": self._encrypt(data_key),
                "key_version": 1,
            }

        if path == "transit/encrypt":
            return {"ciphertext": self._encrypt(base64.b64decode(json["plaintext"]))}

        if path == "transit/decrypt":
            return {"plaintext": base64.b64encode(self._decrypt(json["ciphertext"])).decode("ascii")}

        raise AssertionError(f"Unexpected transit call: {path}")

    def _encrypt(self, plaintext: bytes) -> str:
        if self.asymmetric:
            encrypted = _key_pair().public_key().encrypt(plaintext, _padding())
        else:
            nonce = os.urandom(_NONCE_LENGTH)
            encrypted = nonce + AESGCM(_symmetric_key()).encrypt(nonce, plaintext, None)

        return f"vault:v1:{base64.b64encode(encrypted).decode('ascii')}"

    def _decrypt(self, ciphertext: str) -> bytes:
        encrypted = base64.b64decode(ciphertext.split(":")[2])

        if self.asymmetric:
            return _key_pair().decrypt(encrypted, _padding())

        return AESGCM(_symmetric_key()).decrypt(encrypted[:_NONCE_LENGTH], encrypted[_NONCE_LENGTH:], None)


def _padding() -> padding.OAEP:
    """The padding OpenBao uses, which a ciphertext it is given has to match."""

    return padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
