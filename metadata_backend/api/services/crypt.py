"""Crypt4GH encryption functionality.

Replaces crypt4gh.keys.c4gh.parse_private_key that may raise a SystemExit exception.
"""

import base64
import time
from functools import lru_cache
from io import BytesIO
from typing import BinaryIO, Callable

import httpx
from crypt4gh.keys import c4gh
from crypt4gh.keys.kdf import KDFS, derive_key
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from nacl.public import PrivateKey

from ...conf.c4gh import c4gh_config
from ...helpers.logger import LOG
from ..exceptions import SystemException

C4GH_KEY_LENGTH = 32
_C4GH_CIPHER = b"chacha20_poly1305"  # ChaCha20-Poly1305 (RFC 8439)
_C4GH_NONCE_LENGTH = 12
_C4GH_NONE = b"none"
_C4GH_KEY_CACHE_SECONDS = 3600


@lru_cache(maxsize=8)
def parse_private_key(key: str, passphrase: str | None = None) -> bytes:
    """
    Parse a base64 encoded PEM Crypt4GH private key.

    :param key: The base64 encoded PEM private key.
    :param passphrase: The passphrase the private key is encrypted with, if it is encrypted.
    :raises ValueError: If the key cannot be read.
    :return: The private key.
    """

    data = _decode_pem(key)
    stream = BytesIO(data)
    if data.startswith(c4gh.MAGIC_WORD):
        stream.seek(len(c4gh.MAGIC_WORD))

    private_key = _unlock_private_key(stream, passphrase)

    if len(private_key) != C4GH_KEY_LENGTH:
        raise ValueError(f"The private key is not a {C4GH_KEY_LENGTH} byte Crypt4GH key")
    return private_key


@lru_cache(maxsize=8)
def parse_public_key(key: str) -> bytes:
    """
    Parse a base64 encoded PEM Crypt4GH public key.

    :param key: The base64 encoded PEM public key.
    :raises ValueError: If the key cannot be read.
    :return: The public key.
    """

    public_key = _decode_pem(key)
    if len(public_key) != C4GH_KEY_LENGTH:
        raise ValueError(f"The public key is not a {C4GH_KEY_LENGTH} byte Crypt4GH key")
    return public_key


def generate_private_key() -> bytes:
    """
    Generate a Crypt4GH private key.

    :return: The private key.
    """

    return bytes(PrivateKey.generate())


def public_key_of(private_key: bytes) -> bytes:
    """
    Derive the public key of a Crypt4GH private key.

    :param private_key: The private key.
    :return: The public key.
    """

    return bytes(PrivateKey(private_key).public_key)


def _unlock_private_key(stream: BinaryIO, passphrase: str | None) -> bytes:
    """
    Read a Crypt4GH private key, unlocking it with the passphrase if it is locked.

    Replaces crypt4gh.keys.c4gh.parse_private_key that may raise a SystemExit exception.

    :param stream: The key bytes, positioned after the magic word.
    :param passphrase: The passphrase the private key is locked with, if it is locked.
    :raises ValueError: If the key cannot be read.
    :return: The private key.
    """

    kdfname = c4gh.decode_string(stream)

    if kdfname != _C4GH_NONE and kdfname not in KDFS:
        raise ValueError(f"The private key is derived by an unsupported function: {kdfname.decode()}")

    # A key that names no derivation function carries no options for one. Upstream reads the
    # rounds and the salt out of them here, where a checker cannot see that the two tests of
    # kdfname agree, and a key naming no function but a cipher leaves both unassigned.
    kdfoptions = c4gh.decode_string(stream) if kdfname != _C4GH_NONE else None

    ciphername = c4gh.decode_string(stream)

    private_data: bytes = c4gh.decode_string(stream)

    if ciphername == _C4GH_NONE:
        return private_data  # ignore the comment

    # Else, the data was encrypted.
    if ciphername != _C4GH_CIPHER:
        raise ValueError(f"The private key is locked with an unsupported cipher: {ciphername.decode()}")

    if kdfoptions is None:
        raise ValueError("The private key is locked but names no key derivation function")

    if not passphrase:
        raise ValueError("The private key is locked and no passphrase was given")

    rounds = int.from_bytes(kdfoptions[:4], byteorder="big")
    salt = kdfoptions[4:]

    shared_key = derive_key(kdfname, passphrase.encode("utf-8"), salt, rounds)  # dklen = 32
    nonce = private_data[:_C4GH_NONCE_LENGTH]
    encrypted_data = private_data[_C4GH_NONCE_LENGTH:]

    try:
        private_key: bytes = ChaCha20Poly1305(shared_key).decrypt(nonce, encrypted_data, None)  # No add
    except Exception as ex:
        raise ValueError("The private key could not be unlocked with the given passphrase") from ex

    return private_key


def _decode_pem(key: str) -> bytes:
    """
    Decode a base64 encoded PEM document into the bytes it wraps.

    :param key: The base64 encoded PEM key.
    :raises ValueError: If the key is not a base64 encoded PEM document.
    :return: The key bytes.
    """

    # Not validated to ignore whitespace in the base64 value.
    pem = base64.b64decode(key).decode("utf-8")
    lines = [line.strip().encode("utf-8") for line in pem.splitlines() if line.strip()]
    if len(lines) != 3 or not lines[0].startswith(b"-----BEGIN ") or not lines[-1].startswith(b"-----END "):
        raise ValueError("The key is not a PEM document")

    return base64.b64decode(lines[1])


# Reads the base64 encoded PEM public key from the response.
Crypt4GHPublicKeyReader = Callable[[httpx.Response], str]


class Crypt4GHPublicKeyProvider:
    """Provides a Crypt4GH public key from a remote URL or from an environmental variable."""

    def __init__(self, reader: Crypt4GHPublicKeyReader) -> None:
        """
        Initialise the Crypt4GH public key provider.

        The Crypt4GHConfig is accessed here to check that an
        encryption key has been provided.

        :param reader: Extracts the key out of the response.
        :raises ValidationError: If no encryption key is configured.
        """

        self._config = c4gh_config()
        self._reader = reader
        self._key: bytes | None = None
        self._read_at: float = 0.0

    async def get(self) -> bytes:
        """
        Get the Crypt4GH public key from a remote URL or from an environmental variable.

        :raises SystemException: If the key could not be read.
        :return: The Crypt4GH public key.
        """

        config = self._config

        if config.CRYPT4GH_PUBLIC_KEY_URL:
            # Fetch the public key from a URL.
            return await self._fetch(config.CRYPT4GH_PUBLIC_KEY_URL)

        # Get the public key from CRYPT4GH_PUBLIC_KEY env variable, which the configuration requires
        # when there is no CRYPT4GH_PUBLIC_KEY_URL.
        try:
            return parse_public_key(config.CRYPT4GH_PUBLIC_KEY or "")
        except ValueError as ex:
            LOG.exception("The Crypt4GH key in the CRYPT4GH_PUBLIC_KEY environment variable could not be read.")
            raise SystemException("Service configuration error.") from ex

    async def _fetch(self, url: str) -> bytes:
        """
        Get the public key provided by the URL.

        :param url: The URL providing the public key.
        :raises SystemException: If the key could not be read and no key is cached.
        :return: The public key.
        """

        if self._key is not None and time.monotonic() - self._read_at < _C4GH_KEY_CACHE_SECONDS:
            # Return the cached key.
            return self._key

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, timeout=10)
                response.raise_for_status()
        except Exception as ex:
            return self._cached_key_or_raise(f"Failed to retrieve the Crypt4GH public key from '{url}'.", ex)

        try:
            key = parse_public_key(self._reader(response))
        except Exception as ex:
            return self._cached_key_or_raise(f"The Crypt4GH key retrieved from '{url}' could not be read.", ex)

        self._key, self._read_at = key, time.monotonic()
        return key

    def _cached_key_or_raise(self, message: str, ex: Exception) -> bytes:
        """
        Return the cached public key, or raise if there is none.

        :param message: The error log message.
        :param ex: The exception that resulted in the error.
        :raises SystemException: If there is no cached public key.
        :return: The cached public key.
        """

        if self._key is not None:
            # Return the cached key.
            LOG.exception("%s Using the cached key.", message)
            return self._key

        LOG.exception(message)
        raise SystemException("Failed to read the Crypt4GH public key.") from ex
