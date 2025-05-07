"""Auth API service."""

import hashlib
import hmac
import os
import secrets
import string
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt

JWT_ALGORITHM = "HS256"
JWT_ISSUER = "SD Submit"
JWT_SECRET_ENV = "JWT_SECRET"  # nosec

API_KEY_LENGTH = 32


class AccessService:
    """Auth API service."""

    def __init__(self) -> None:
        """Initialize the service."""
        self.api_keys: dict[str, Any] = {}  # TODO(authentication): replace in-memory API key store

    @staticmethod
    def create_jwt_token(user_id: str, expiration: timedelta) -> str:
        """
        Generate a signed JWT token for the given user ID.

        The token includes standard claims: subject (`sub`), expiration (`exp`),
        issued-at (`iat`), and issuer (`iss`).

        Args:
            user_id (str): The unique identifier of the user (used as the 'sub' claim).
            expiration (timedelta): How long the token should be valid for.

        Returns:
            str: The signed JWT token.

        Raises:
            RuntimeError: If the JWT secret is not set in environment variables.
        """
        jwt_secret = os.getenv(JWT_SECRET_ENV)
        if not jwt_secret:
            raise RuntimeError(f"{JWT_SECRET_ENV} environment variable is undefined.")

        now = datetime.now(timezone.utc)
        exp_time = now + expiration

        payload = {
            "sub": user_id,
            "exp": exp_time,
            "iat": now,
            "iss": JWT_ISSUER,
        }

        return jwt.encode(payload, jwt_secret, algorithm=JWT_ALGORITHM)

    @staticmethod
    def read_jwt_token(token: str) -> str:
        """
        Decode and verify the JWT token, returning the user ID (`sub` claim).

        Args:
            token (str): The JWT token string to decode.

        Returns:
            str: The user ID extracted from the `sub` claim.

        Raises:
            RuntimeError: If the JWT secret is not set.
            PyJWTError: If the token has expired, is malformed or fails verification.
        """
        jwt_secret = os.getenv(JWT_SECRET_ENV)
        if not jwt_secret:
            raise RuntimeError(f"{JWT_SECRET_ENV} environment variable is undefined.")

        decoded = jwt.decode(
            token,
            jwt_secret,
            algorithms=[JWT_ALGORITHM],
            issuer=JWT_ISSUER,
        )
        return str(decoded["sub"])

    def _hash_api_key(self, api_key: str, salt: str) -> str:
        """Hashes the API key with a salt using SHA-256."""
        return hashlib.sha256((api_key + salt).encode("utf-8")).hexdigest()

    def _generate_salt(self) -> str:
        """Generate a random salt for each API key."""
        return secrets.token_hex(16)  # Generate a 16-byte salt (32 hex characters)

    def create_api_key(self, user_id: str, key_id: str) -> str:
        """Create a cryptographically secure random API key and store its hash.

        Args:
            user_id: The ID of the user whose API key is being created.
            key_id: A unique key identifier for the user.

        Returns:
            str: The plain-text API key.
        """
        alphabet = string.ascii_letters + string.digits
        api_key = "".join(secrets.choice(alphabet) for _ in range(API_KEY_LENGTH))

        # Generate a salt and hash the API key
        salt = self._generate_salt()
        hashed_key = self._hash_api_key(api_key, salt)

        # Save the hashed API key and salt (not the original API key)

        # TODO(authentication): replace in-memory API key store
        if user_id not in self.api_keys:
            self.api_keys[user_id] = {}
        self.api_keys[user_id][key_id] = {"hash": hashed_key, "salt": salt}

        return api_key  # Return the plain-text key only for the user (never store this in the database)

    def validate_api_key(self, user_id: str, api_key: str) -> bool:
        """Validate the provided API key by comparing it with the stored hash.

        Args:
            user_id: The ID of the user whose API key is being validated.
            api_key: The plain-text API key to validate.

        Returns:
            bool: True if the API key is valid, False otherwise.
        """

        # TODO(authentication): replace in-memory API key store
        if user_id in self.api_keys:
            for key_id in self.api_keys[user_id]:
                stored_data = self.api_keys[user_id][key_id]
                stored_hash = stored_data["hash"]
                salt = stored_data["salt"]

                # Hash the provided API key with the stored salt and compare the hashes
                if hmac.compare_digest(stored_hash, self._hash_api_key(api_key, salt)):
                    return True
        return False

    def revoke_api_key(self, user_id: str, key_id_or_api_key: str) -> bool:
        """Revoke an API key by removing it from the storage.

        Args:
            user_id: The ID of the user whose API key is being revoked.
            key_id_or_api_key: The unique key ID or API key to revoke.

        Returns:
            bool: True if the API key was removed, False otherwise.
        """

        # TODO(authentication): replace in-memory API key store
        if user_id in self.api_keys:
            for key_id in self.api_keys[user_id]:
                if key_id == key_id_or_api_key:
                    del self.api_keys[user_id][key_id]
                    return True

                stored_data = self.api_keys[user_id][key_id]
                stored_hash = stored_data["hash"]
                salt = stored_data["salt"]

                # Hash the provided API key with the stored salt and compare the hashes
                if stored_hash == self._hash_api_key(key_id_or_api_key, salt):
                    del self.api_keys[user_id][key_id]
                    return True

        return False

    def list_api_keys(self, user_id: str) -> list[str]:
        """List all API keys (key_ids) for a given user.

        Args:
            user_id: The ID of the user whose API keys are being listed.

        Returns:
            list: A list of key IDs associated with the user.
        """
        if user_id in self.api_keys:
            return list(self.api_keys[user_id].keys())
        return []
