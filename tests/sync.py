"""Signing the sync tokens the tests authenticate with.

The sync service account signs these with its own private key, so nothing in the submitter
signs one outside the tests.
"""

import base64
import hashlib
import hmac
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)

from metadata_backend.api.dependencies import SYNC_TOKEN_ALGORITHM

SYNC_TOKEN_LIFETIME = timedelta(seconds=60)


def sync_key_pair() -> tuple[str, str]:
    """
    Generate a key pair of the kind the sync tokens are signed with.

    Generated rather than stored, so no test key can be mistaken for a deployed one.

    :return: The PEM private key to sign with, and the PEM public key to verify with.
    """

    key = ec.generate_private_key(ec.SECP256R1())
    private_key = key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())
    public_key = key.public_key().public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo)
    return private_key.decode("utf-8"), public_key.decode("utf-8")


def base64_public_keys(*public_keys: str) -> str:
    """
    Encode public keys the way a sync client's key is configured.

    :param public_keys: The PEM public keys, all of which are to be accepted.
    :return: The base64-encoded keys, one after another.
    """

    return base64.b64encode("".join(public_keys).encode("utf-8")).decode("ascii")


def sync_clients(*clients: tuple[str, ...]) -> str:
    """
    Encode sync clients the way SYNC_CLIENTS is configured.

    :param clients: Each client as its iss claim followed by its PEM public keys.
    :return: The JSON array of the clients.
    """

    return json.dumps(
        [{"iss": iss, "public_keys": [base64_public_keys(key) for key in keys]} for iss, *keys in clients]
    )


def sync_headers(token: str) -> dict[str, str]:
    """
    The authorization header carrying a sync token.

    :param token: The token to authorize with.
    :return: The header.
    """

    return {"Authorization": f"Bearer {token}"}


def sync_claims(audience: str, issuer: str, lifetime: timedelta = SYNC_TOKEN_LIFETIME) -> dict[str, Any]:
    """
    The claims of a sync token the submitter accepts.

    :param audience: The audience to issue the token for.
    :param issuer: The issuer to issue the token by.
    :param lifetime: How long the token is valid, which a negative value has already expired.
    :return: The claims, for a test to sign as they are or to alter first.
    """

    issued_at = datetime.now(timezone.utc)
    return {
        "iss": issuer,
        "sub": issuer,
        "aud": audience,
        "iat": issued_at,
        "exp": issued_at + lifetime,
        "jti": uuid.uuid4().hex,
    }


def sign_sync_token(claims: dict[str, Any], key: str, algorithm: str = SYNC_TOKEN_ALGORITHM) -> str:
    """
    Sign the claims of a sync token.

    :param claims: The claims to sign.
    :param key: The key to sign with, a private key unless the algorithm says otherwise.
    :param algorithm: The algorithm to sign with, for asserting which ones are accepted.
    :return: The signed token.
    """

    return jwt.encode(claims, key, algorithm=algorithm)


def _base64url(data: bytes) -> str:
    """Encode the way a JWT encodes its parts."""

    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def hmac_signed_sync_token(claims: dict[str, Any], secret: str) -> str:
    """
    Sign the claims with the secret as an HMAC key, claiming HS256 in the header.

    Built by hand because PyJWT refuses to sign HS256 with a PEM key, which is the forgery a
    verifier accepting whichever algorithm its token names would take: the public key it holds
    is all the attacker needs as the secret.

    :param claims: The claims to sign.
    :param secret: The secret to sign with, being the public key the verifier holds.
    :return: The signed token.
    """

    encoded = {
        claim: int(value.timestamp()) if isinstance(value, datetime) else value for claim, value in claims.items()
    }
    signing_input = ".".join(
        (
            _base64url(json.dumps({"alg": "HS256", "typ": "JWT"}).encode("utf-8")),
            _base64url(json.dumps(encoded).encode("utf-8")),
        )
    )
    signature = hmac.new(secret.encode("utf-8"), signing_input.encode("ascii"), hashlib.sha256).digest()
    return f"{signing_input}.{_base64url(signature)}"
