"""Service for issuing JWT tokens and API keys."""

import hashlib
import hmac
import secrets
import string
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from aiohttp import web

from ...conf.oidc import oidc_config
from ...database.postgres.models import ApiKeyEntity
from ...database.postgres.repositories.api_key import ApiKeyRepository
from ...helpers.logger import LOG
from ..models.models import ApiKey

JWT_ALGORITHM = "HS256"
JWT_ISSUER = "SD Submit"
JWT_EXPIRATION = timedelta(days=7)

API_KEY_ID_LENGTH = 12
API_KEY_LENGTH = 32


class AuthService:
    """Service for issuing JWT tokens and API keys."""

    def __init__(self, repository: ApiKeyRepository) -> None:
        """Initialize the service."""
        self.__repository = repository

    @staticmethod
    async def create_jwt_token_from_userinfo(userinfo: dict[str, Any]) -> str:
        """
        Generate a signed JWT token from /userinfo response.

        :param userinfo: OIDC /userinfo response.
        :returns: The signed JWT token
        :raises HTTPUnauthorized: If the required claims are not found.
        """
        # Extract user ID.
        if "CSCUserName" in userinfo:
            user_id = userinfo["CSCUserName"]
        elif "remoteUserIdentifier" in userinfo:
            user_id = userinfo["remoteUserIdentifier"]
        elif "sub" in userinfo:
            user_id = userinfo["sub"]
        else:
            reason = "Authenticated user is missing required claims."
            LOG.error(reason)
            raise web.HTTPUnauthorized(reason="reason")

        # Extract user name, fallback to user_id if not available.
        given_name = userinfo.get("given_name", "").strip()
        family_name = userinfo.get("family_name", "").strip()

        if given_name or family_name:
            user_name = f"{given_name} {family_name}".strip()
        else:
            user_name = user_id

        return AuthService.create_jwt_token(user_id, user_name)

    @staticmethod
    def create_jwt_token(user_id: str, user_name: str, expiration: timedelta = JWT_EXPIRATION) -> str:
        """
        Generate a signed JWT token.

        Args:
            user_id: The unique identifier of the user used in the 'sub' claim.
            user_name: The name of the user.
            expiration: How long should the token be valid.

        Returns:
            str: The signed JWT token.
        """

        now = datetime.now(timezone.utc)
        exp_time = now + expiration

        payload = {
            "sub": user_id,
            "user_name": user_name,
            "exp": exp_time,
            "iat": now,
            "iss": JWT_ISSUER,
        }

        return jwt.encode(payload, oidc_config().JWT_SECRET, algorithm=JWT_ALGORITHM)

    @staticmethod
    def validate_jwt_token(token: str) -> tuple[str, str]:
        """
        Decode and verify the JWT token, returning the user ID and user name.

        Args:
            token: The JWT token string to decode.

        Returns:
             The user ID from the `sub` claim, and the user name from the `user_name` claim.

        Raises:
            RuntimeError: If the JWT secret is not set.
            PyJWTError: If the token has expired, is malformed or fails verification.
        """
        decoded = jwt.decode(
            token,
            oidc_config().JWT_SECRET,
            algorithms=[JWT_ALGORITHM],
            issuer=JWT_ISSUER,
        )
        return str(decoded["sub"]), str(decoded["user_name"])

    @staticmethod
    def _hash_api_key(api_key: str, salt: str) -> str:
        """Hashes the API key with a salt using SHA-256."""
        return hashlib.sha256((api_key + salt).encode("utf-8")).hexdigest()

    @staticmethod
    def _generate_salt() -> str:
        """Generate a random salt for each API key."""
        return secrets.token_hex(16)  # Generate a 16-byte salt (32 hex characters)

    @staticmethod
    def _generate_api_key_id() -> str:
        """Generate a fixed length hex key id ."""
        n_bytes = API_KEY_ID_LENGTH // 2
        return secrets.token_hex(n_bytes)

    async def create_api_key(self, user_id: str, key_id: str) -> str:
        """
        Create a cryptographically secure random API key.

        Returns a plain-text API key prefixed with a generated API key id.

        Args:
            user_id: The ID of the user whose API key is being created.
            key_id: The unique key id assigned by the user.

        Returns:
            str: The plain-text API key prefixed with the API key id.
        """
        # The API key given to the user is prefixed with the generated key id used to
        # identify and retrieve the key. The API key can't be used to retrieve the key
        # because when it is stored it is hashed with a salt.
        generated_key_id = self._generate_api_key_id()

        # Generate API key and hash it using random salt.
        alphabet = string.ascii_letters + string.digits
        api_key = "".join(secrets.choice(alphabet) for _ in range(API_KEY_LENGTH))
        salt = self._generate_salt()
        hashed_api_key = self._hash_api_key(api_key, salt)

        # Save the hashed API key and salt (not the original API key)
        try:
            await self.__repository.add_api_key(
                ApiKeyEntity(
                    key_id=generated_key_id,
                    user_id=user_id,
                    user_key_id=key_id,
                    api_key=hashed_api_key,
                    salt=salt,
                    created_at=datetime.now(timezone.utc),
                )
            )
        except Exception as exc:
            msg = str(exc).lower()
            if "duplicate key value violates unique constraint" in msg:
                raise web.HTTPBadRequest(reason="API key already exists with this key id.") from exc
            raise web.HTTPInternalServerError(reason="Failed to create API key.") from exc

        # Return the plain text API key prefixed with the API key id.
        return f"{generated_key_id}.{api_key}"

    async def validate_api_key(self, api_key: str) -> str | None:
        """
        Validate the provided API key by comparing it with the stored hash.

        The API key must be prefixed with the generated API key id.

        Args:
            api_key: The plain-text API key prefixed with the generated API key id.

        Returns:
            User id if the API key is valid. None otherwise.
        """

        # Extract generated key ID.
        parts = api_key.split(".", 1)
        if len(parts) != 2:
            return None
        key_id, api_key = parts

        key = await self.__repository.get_api_key(key_id)

        if key is None:
            return None

        # Compare the API key hash.
        if hmac.compare_digest(key.api_key, self._hash_api_key(api_key, key.salt)):
            return key.user_id

        return None

    async def revoke_api_key(self, user_id: str, key_id: str) -> None:
        """Revoke an API key by removing it.

        Args:
            user_id: The ID of the user whose API key is being revoked.
            key_id: The unique key id assigned by the user.
        """

        await self.__repository.delete_api_key(user_id, key_id)

    async def list_api_keys(self, user_id: str) -> list[ApiKey]:
        """List API keys for a given user.

        Args:
            user_id: The ID of the user whose API keys are being listed.

        Returns:
            list: A list of API keys associated with the user.
        """

        return await self.__repository.get_api_keys(user_id)
