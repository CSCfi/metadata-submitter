"""Metadata object encryption with OpenBao.

An encrypted metadata object begins with magic bytes, encryption method and
the encryption key name:

    magic(9) | kind(1) | key_name_length(1) | key_name | body

    magic     The word SDSUBMIT followed by a version number for this layout.
    kind      The encryption method.
    key_name  The OpenBao encryption key name.
    body      The encrypted metadata object.

The two supported encryption methods are:

    envelope  OpenBao generates a data encryption key for this one object. The
              document is encrypted with that key, while the key itself is
              encrypted by OpenBao under a key encryption key. The stored
              object contains both the encrypted data encryption key,
              and the encrypted document.

    direct    The document is sent to OpenBao and comes back encrypted. The
              stored object contains the encrypted document. Only a symmetric
              encryption key can be used for direct encryption. An asymmetric
              key encryption key can only encrypt at most a few hundred bytes.
"""

import asyncio
import base64
import os
import time
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from starlette import status
from yarl import URL

from ...conf.openbao import DIRECT, OpenBaoConfig, openbao_config
from ...helpers.logger import LOG
from ...services.service_handler import ServiceHandler
from ..exceptions import ServiceHandlerSystemException, SystemException

SD_SUBMIT_MAGIC = b"SDSUBMIT\x01"

# Service name for the OpenBao health handler.
_SERVICE_NAME = "openbao"

_K8_SERVICE_ACCOUNT_TOKEN_PATH = Path("/var/run/secrets/kubernetes.io/serviceaccount/token")
_K8_LEASE_FRACTION = 0.8

# The encryption method.
_ENVELOPE_KIND = 1
_DIRECT_KIND = 2

# The key encryption key name.
_KEY_NAME_LENGTH_BYTES = 1
_MAX_KEY_NAME_LENGTH = 256**_KEY_NAME_LENGTH_BYTES - 1

# The data encryption key length.
_DATA_KEY_LENGTH_BYTES = 2
_MAX_DATA_KEY_LENGTH = 256**_DATA_KEY_LENGTH_BYTES - 1

# AES-GCM is used to encrypt the metadata object in envelope encryption.

# The length of the AES-GCM data encryption key (AES-256) in bits.
_DATA_KEY_BITS = 256

# Defines a 12-byte (96-bit) Initialization Vector (IV). NIST recommends 12 bytes for AES-GCM.
_NONCE_LENGTH = 12

# Defines a 16-byte (128-bit) Authentication Tag. This is the maximum tag length for AES-GCM.
_TAG_LENGTH = 16


def is_encrypted(data: bytes) -> bool:
    """
    Check if a stored metadata object is encrypted.

    :param data: The stored metadata object.
    :return: True if the metadata object is encrypted.
    """

    return data.startswith(SD_SUBMIT_MAGIC)


class OpenBaoService(ServiceHandler):
    """Encrypts and decrypts metadata objects using the OpenBao transit secrets engine."""

    def __init__(self, config: OpenBaoConfig | None = None) -> None:
        """
        Initialise the OpenBao service.

        :param config: The OpenBao configuration. Defaults to reading it from the environment.
        :raises SystemException: If the configuration cannot be used to encrypt objects.
        """

        self._config = config or openbao_config()

        if not self._config.OPENBAO_URL or not self._config.OPENBAO_OBJECT_KEY_NAME:
            raise SystemException("OPENBAO_URL and OPENBAO_OBJECT_KEY_NAME are required to encrypt metadata objects.")

        self._url = self._config.OPENBAO_URL
        self._key_name = self._config.OPENBAO_OBJECT_KEY_NAME

        if not self._key_name.isascii() or len(self._key_name) > _MAX_KEY_NAME_LENGTH:
            raise SystemException(f"OPENBAO_OBJECT_KEY_NAME must be at most {_MAX_KEY_NAME_LENGTH} ASCII characters.")

        base_url = URL(self._url.rstrip("/")) / "v1"
        super().__init__(
            _SERVICE_NAME,
            base_url,
            http_client_timeout=10,
            healthcheck_url=base_url / "sys/health",
        )

        self._k8_login_token: str | None = None
        self._k8_login_until: float = 0.0
        self._k8_login_lock = asyncio.Lock()

    async def validate(self) -> None:
        """
        Check that the encryption key exists and suits how objects are encrypted.

        Called once when the service starts, so that a key that is missing or of the
        wrong kind is reported then rather than by the first metadata object.

        :raises SystemException: If the key cannot be used to encrypt objects.
        """

        key = await self._read_key()
        encryption = self._config.OPENBAO_OBJECT_ENCRYPTION
        asymmetric = _is_asymmetric(key)

        if encryption == DIRECT and asymmetric:
            raise SystemException(
                f"OPENBAO_OBJECT_ENCRYPTION '{DIRECT}' requires a symmetric OPENBAO_OBJECT_KEY_NAME, and "
                f"'{self._key_name}' is asymmetric. An asymmetric key encrypts a few hundred bytes "
                f"at most, which a metadata object exceeds."
            )

        LOG.info(
            "Metadata objects are encrypted with OpenBao using %s encryption under the %s key '%s'.",
            encryption,
            "asymmetric" if asymmetric else "symmetric",
            self._key_name,
        )

    async def encrypt(self, document: str) -> bytes:
        """
        Encrypt a metadata object in the way this deployment is configured to.

        :param document: The metadata object document.
        :return: The stored metadata object.
        """

        if self._config.OPENBAO_OBJECT_ENCRYPTION == DIRECT:
            return await self.encrypt_direct(document)

        return await self.encrypt_envelope(document)

    async def encrypt_envelope(self, document: str) -> bytes:
        """
        Encrypt a metadata object under a data encryption key generated by OpenBao.

        :param document: The metadata object document.
        :return: The stored metadata object.
        """

        # Ask OpenBao to generate a data encryption key. OpenBao returns
        # the plaintext version of that key and a version encrypted by
        # the key management key defined by OPENBAO_OBJECT_KEY_NAME.
        data = await self._transit(self._key_name, "transit/datakey/plaintext", {"bits": _DATA_KEY_BITS})
        data_key = base64.b64decode(data["plaintext"])
        encrypted_data_key = str(data["ciphertext"])

        body = _write_envelope(encrypted_data_key, _encrypt_document(data_key, document))
        return _write_object(self._key_name, _ENVELOPE_KIND, body)

    async def encrypt_direct(self, document: str) -> bytes:
        """
        Encrypt a metadata object by sending the document to OpenBao.

        :param document: The metadata object document.
        :return: The stored metadata object.
        """

        ciphertext = await self._transit_encrypt(document.encode("utf-8"))
        return _write_object(self._key_name, _DIRECT_KIND, ciphertext.encode("ascii"))

    async def decrypt(self, data: bytes) -> str:
        """
        Decrypt a stored metadata object.

        :param data: The stored metadata object.
        :raises SystemException: If the object cannot be decrypted.
        :return: The metadata object document.
        """

        kind, key_name, body = _read_object(data)

        if kind == _ENVELOPE_KIND:
            encrypted_data_key, ciphertext = _read_envelope(body)
            # Ask OpenBao to return the plaintext version of the data encryption key.
            data_key = await self._transit_decrypt(key_name, encrypted_data_key)
            return _decrypt_document(data_key, ciphertext)

        if kind == _DIRECT_KIND:
            document = await self._transit_decrypt(key_name, body.decode("ascii"))
            return document.decode("utf-8")

        raise SystemException(f"The stored metadata object was encrypted in an unknown way: {kind}.")

    async def _auth_headers(self) -> dict[str, str]:
        """
        Return a header with the OpenBao authentication token.

        :raises SystemException: If logging in fails.
        :return: The token header.
        """

        if self._config.OPENBAO_TOKEN:
            # Use a static token.
            return {"X-Vault-Token": self._config.OPENBAO_TOKEN}

        async with self._k8_login_lock:
            # Use a k8 service token.
            if self._k8_login_token is None or time.monotonic() >= self._k8_login_until:
                self._k8_login_token, self._k8_login_until = await self._k8_login()
            token = self._k8_login_token

        return {"X-Vault-Token": token}

    async def _k8_login(self) -> tuple[str, float]:
        """
        Exchange the Kubernetes pod's service account token for an OpenBao token.

        :raises SystemException: If the service account token cannot be read, or
            OpenBao refuses it.
        :return: The token and the time to stop using it.
        """

        mount = self._config.OPENBAO_KUBERNETES_MOUNT

        try:
            jwt = _K8_SERVICE_ACCOUNT_TOKEN_PATH.read_text(encoding="utf-8").strip()
        except OSError as ex:
            LOG.exception(
                "Failed to read the Kubernetes service account token at '%s'.", _K8_SERVICE_ACCOUNT_TOKEN_PATH
            )
            raise SystemException("Failed to read the Kubernetes service account token.") from ex

        message = f"Failed to log in to OpenBao as '{self._config.OPENBAO_KUBERNETES_ROLE}' at 'auth/{mount}'."

        try:
            response = await self._request(
                method="POST",
                path=f"auth/{mount}/login",
                json_data={"role": self._config.OPENBAO_KUBERNETES_ROLE, "jwt": jwt},
                log_payload=False,
            )
            auth = response["auth"]
            token = str(auth["client_token"])
            lease = int(auth["lease_duration"])
        except ServiceHandlerSystemException:
            LOG.error(message)
            raise
        except Exception as ex:
            LOG.exception(message)
            raise SystemException("Failed to log in to OpenBao.") from ex

        LOG.info("Logged in to OpenBao as '%s', for %d seconds.", self._config.OPENBAO_KUBERNETES_ROLE, lease)
        return token, time.monotonic() + lease * _K8_LEASE_FRACTION

    async def _read_key(self) -> dict[str, Any]:
        """
        Read the configured OpenBao encryption key.

        :raises SystemException: If the key cannot be read.
        :return: The key metadata, including the public half of an asymmetric key.
        """

        return await self._openbao_request(
            f"Failed to read the OpenBao key encryption key '{self._key_name}'.",
            method="GET",
            path=f"transit/keys/{self._key_name}",
        )

    async def _transit_encrypt(self, plaintext: bytes) -> str:
        """
        Ask OpenBao to encrypt the document using a symmetric key.

        :param plaintext: What to encrypt.
        :return: The OpenBao ciphertext.
        """

        data = await self._transit(
            self._key_name, "transit/encrypt", {"plaintext": base64.b64encode(plaintext).decode("ascii")}
        )
        return str(data["ciphertext"])

    async def _transit_decrypt(self, key_name: str, ciphertext: str) -> bytes:
        """
        Ask OpenBao to decrypt the document using a symmetric key.

        :param key_name: The name of the key encryption key.
        :param ciphertext: The OpenBao ciphertext.
        :return: What it was made from.
        """

        data = await self._transit(key_name, "transit/decrypt", {"ciphertext": ciphertext})
        return base64.b64decode(data["plaintext"])

    async def _transit(self, key_name: str, path: str, json: dict[str, Any]) -> dict[str, Any]:
        """
        Call the OpenBao transit secrets engine.

        :param key_name: The name of the encryption key.
        :param path: The endpoint path.
        :param json: The request body.
        :raises SystemException: If the call fails.
        :return: The data of the response.
        """

        return await self._openbao_request(
            f"The OpenBao request to '{path}' for key '{key_name}' failed.",
            method="POST",
            path=f"{path}/{key_name}",
            json_data=json,
        )

    async def _openbao_request(
        self,
        message: str,
        *,
        method: str,
        path: str,
        json_data: dict[str, Any] | None = None,
        login_again: bool = True,
    ) -> dict[str, Any]:
        """
        Make an authenticated OpenBao request, and return the data of the response.

        If OpenBao refuses the login token, and if Kubernetes service account
        authentication is being used, then attempts to log in again using the
        latest Kubernetes service account token.

        :param message: Error message to log if the request fails.
        :param method: The HTTP method.
        :param path: The request path.
        :param json_data: The request body.
        :param login_again: Whether to log in again if OpenBao refuses the login token.
        :raises SystemException: If the request fails.
        :return: The data field of the response.
        """

        headers = await self._auth_headers()
        try:
            response = await self._request(
                method=method, path=path, json_data=json_data, headers=headers, log_payload=False
            )
        except ServiceHandlerSystemException as ex:
            # OpenBao returns 403 when the token is no longer valid or accepted.
            if (
                login_again
                and ex.service_status_code == status.HTTP_403_FORBIDDEN
                and self._config.OPENBAO_KUBERNETES_ROLE
            ):
                LOG.warning("OpenBao refused the login token. Logging in again.")
                # Forget the refused token to trigger a new login attempt.
                if self._k8_login_token == headers["X-Vault-Token"]:
                    self._k8_login_token = None
                return await self._openbao_request(
                    message, method=method, path=path, json_data=json_data, login_again=False
                )
            LOG.error(message)
            raise

        data: dict[str, Any] = response["data"]
        return data


def _is_asymmetric(key: dict[str, Any]) -> bool:
    """
    Check whether an encryption key is asymmetric.

    OpenBao lists a public half for each version of an asymmetric key, and only a
    creation time for each version of a symmetric one.

    :param key: The key metadata, as OpenBao returns it.
    :raises SystemException: If the metadata names no key versions.
    :return: True if the key is asymmetric.
    """

    versions = key.get("keys") or {}
    if not versions:
        raise SystemException(f"OpenBao returned no key versions for '{key.get('name')}'.")

    return any(isinstance(version, dict) and "public_key" in version for version in versions.values())


def _encrypt_document(data_key: bytes, document: str) -> bytes:
    """
    Encrypt a document with AES-GCM under a data encryption key.

    :param data_key: The data encryption key.
    :param document: The metadata object document.
    :return: The nonce, the encrypted document and the authentication tag.
    """

    nonce = os.urandom(_NONCE_LENGTH)
    ciphertext = AESGCM(data_key).encrypt(nonce, document.encode("utf-8"), None)
    return nonce + ciphertext


def _decrypt_document(data_key: bytes, ciphertext: bytes) -> str:
    """
    Decrypt what `_encrypt_document` wrote.

    :param data_key: The data encryption key.
    :param ciphertext: The nonce, the encrypted document and the authentication tag.
    :raises SystemException: If the document cannot be decrypted.
    :return: The metadata object document.
    """

    try:
        document = AESGCM(data_key).decrypt(ciphertext[:_NONCE_LENGTH], ciphertext[_NONCE_LENGTH:], None)
    except Exception as ex:
        LOG.exception("A stored metadata object could not be decrypted with its data encryption key.")
        raise SystemException("Failed to decrypt a stored metadata object.") from ex

    return document.decode("utf-8")


def _write_object(key_name: str, kind: int, body: bytes) -> bytes:
    """
    Write an encrypted metadata object including magic bytes, encryption method and
    the encryption key name.

    :param key_name: The name of the key encryption key it was encrypted under.
    :param kind: Which way it was encrypted.
    :param body: What that way produced.
    :return: The stored metadata object.
    """

    name = key_name.encode("ascii")
    return SD_SUBMIT_MAGIC + bytes([kind]) + len(name).to_bytes(_KEY_NAME_LENGTH_BYTES, "big") + name + body


def _read_ascii(value: bytes) -> str:
    """
    Read a field written as ASCII.

    :param value: The field.
    :raises SystemException: If the field is not ASCII.
    :return: The field as text.
    """

    try:
        return value.decode("ascii")
    except UnicodeDecodeError as ex:
        raise SystemException("The stored metadata object is malformed.") from ex


def _read_object(data: bytes) -> tuple[int, str, bytes]:
    """
    Read what `_write_object` wrote.

    :param data: The stored metadata object.
    :raises SystemException: If the object is not encrypted or is truncated.
    :return: The encryption method, the encryption key name, and the body.
    """

    if not is_encrypted(data):
        raise SystemException("The stored metadata object is not encrypted with OpenBao.")

    # Where each field of the header begins.
    kind_at = len(SD_SUBMIT_MAGIC)
    name_length_at = kind_at + 1
    name_at = name_length_at + _KEY_NAME_LENGTH_BYTES

    if len(data) < name_at:
        raise SystemException("The stored metadata object is truncated.")

    name_length = int.from_bytes(data[name_length_at:name_at], "big")
    name = data[name_at : name_at + name_length]

    if len(name) != name_length:
        raise SystemException("The stored metadata object is truncated.")

    return data[kind_at], _read_ascii(name), data[name_at + name_length :]


def _write_envelope(encrypted_data_key: str, ciphertext: bytes) -> bytes:
    """
    Write the body of an envelope: an encrypted data encryption key, then the document.

    :param encrypted_data_key: The data encryption key, encrypted by OpenBao.
    :param ciphertext: The document encrypted under that data encryption key.
    :raises SystemException: If the encrypted data encryption key is too long to store.
    :return: The body of an envelope.
    """

    data_key = encrypted_data_key.encode("ascii")

    if len(data_key) > _MAX_DATA_KEY_LENGTH:
        raise SystemException(
            f"OpenBao returned an encrypted data encryption key of {len(data_key)} bytes, more "
            f"than the {_MAX_DATA_KEY_LENGTH} a stored metadata object can hold."
        )

    return len(data_key).to_bytes(_DATA_KEY_LENGTH_BYTES, "big") + data_key + ciphertext


def _read_envelope(body: bytes) -> tuple[str, bytes]:
    """
    Read what `_write_envelope` wrote.

    :param body: The body of an envelope.
    :raises SystemException: If the body is truncated.
    :return: The encrypted data encryption key and the encrypted document.
    """

    if len(body) < _DATA_KEY_LENGTH_BYTES:
        raise SystemException("The stored metadata object is truncated.")

    # Where the encrypted data encryption key begins, and where the document does.
    encrypted_data_key_at = _DATA_KEY_LENGTH_BYTES
    encrypted_data_key_length = int.from_bytes(body[:encrypted_data_key_at], "big")
    ciphertext_at = encrypted_data_key_at + encrypted_data_key_length

    encrypted_data_key = body[encrypted_data_key_at:ciphertext_at]
    ciphertext = body[ciphertext_at:]

    if len(encrypted_data_key) != encrypted_data_key_length or len(ciphertext) < _NONCE_LENGTH + _TAG_LENGTH:
        raise SystemException("The stored metadata object is truncated.")

    return _read_ascii(encrypted_data_key), ciphertext
