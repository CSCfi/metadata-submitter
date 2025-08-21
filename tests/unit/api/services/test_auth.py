import os
from datetime import timedelta
from typing import Iterator
from unittest.mock import patch

import jwt
import pytest
from pydantic import BaseModel

from metadata_backend.api.services.auth import (
    API_KEY_ID_LENGTH,
    API_KEY_LENGTH,
    JWT_ALGORITHM,
    JWT_ISSUER,
    JWT_SECRET_ENV,
    AccessService,
)
from metadata_backend.database.postgres.repositories.api_key import ApiKeyRepository
from metadata_backend.database.postgres.repository import create_engine, create_session_factory, transaction


class JwtConfig(BaseModel):
    user_id: str
    user_name: str
    expiration: timedelta
    jwt_secret: str


@pytest.fixture
def jwt_config() -> Iterator[JwtConfig]:
    config = JwtConfig(
        user_id="mock-user",
        user_name="mock-user-name",
        expiration=timedelta(minutes=10),
        jwt_secret="mock-secret",
    )
    env_patcher = patch.dict(os.environ, {JWT_SECRET_ENV: config.jwt_secret})
    env_patcher.start()
    yield config
    env_patcher.stop()


@pytest.fixture
async def service() -> AccessService:
    engine = await create_engine()
    session_factory = create_session_factory(engine)
    return AccessService(ApiKeyRepository(session_factory))


def test_create_jwt_token_contains_required_claims(jwt_config) -> None:
    token = AccessService.create_jwt_token(jwt_config.user_id, jwt_config.user_name, jwt_config.expiration)
    decoded = jwt.decode(token, jwt_config.jwt_secret, algorithms=[JWT_ALGORITHM], issuer=JWT_ISSUER)

    assert decoded["sub"] == jwt_config.user_id
    assert decoded["user_name"] == jwt_config.user_name
    assert decoded["iss"] == JWT_ISSUER
    assert "exp" in decoded
    assert "iat" in decoded


def test_read_jwt_token_returns_user_id(jwt_config) -> None:
    token = AccessService.create_jwt_token(jwt_config.user_id, jwt_config.user_name, jwt_config.expiration)
    user_id, user_name = AccessService.validate_jwt_token(token)
    assert user_id == jwt_config.user_id
    assert user_name == jwt_config.user_name


def test_create_jwt_token_missing_secret_raises(jwt_config) -> None:
    os.environ.pop(JWT_SECRET_ENV, None)
    with pytest.raises(RuntimeError):
        AccessService.create_jwt_token(jwt_config.user_id, jwt_config.user_name, jwt_config.expiration)


def test_read_jwt_token_missing_secret_raises(jwt_config) -> None:
    token = AccessService.create_jwt_token(jwt_config.user_id, jwt_config.user_name, jwt_config.expiration)
    os.environ.pop(JWT_SECRET_ENV, None)
    with pytest.raises(RuntimeError):
        AccessService.validate_jwt_token(token)


def test_read_invalid_jwt_token_raises(jwt_config) -> None:
    invalid_token = "invalid"
    with pytest.raises(jwt.InvalidTokenError):
        AccessService.validate_jwt_token(invalid_token)


def test_read_expired_jwt_token_raises(jwt_config) -> None:
    expired_token = AccessService.create_jwt_token(jwt_config.user_id, jwt_config.user_name, timedelta(seconds=-1))
    with pytest.raises(jwt.ExpiredSignatureError):
        AccessService.validate_jwt_token(expired_token)


def test_read_wrong_issuer_jwt_token_raises(jwt_config, session_factory) -> None:
    token = AccessService.create_jwt_token(jwt_config.user_id, jwt_config.user_name, jwt_config.expiration)
    with pytest.raises(jwt.InvalidIssuerError):
        jwt.decode(token, os.getenv(JWT_SECRET_ENV), algorithms=["HS256"], issuer="invalid")


async def test_hash_api_key(jwt_config, service, session_factory) -> None:
    """Test the API key hash algorithm."""
    async with transaction(session_factory, requires_new=True, rollback_new=True):
        user_id = "test-user"
        key_id = "test-key"

        api_key = await service.create_api_key(user_id, key_id)
        salt = "mysalt456"

        # Hash should be deterministic
        hash1 = service._hash_api_key(api_key, salt)
        hash2 = service._hash_api_key(api_key, salt)

        assert hash1 == hash2
        assert len(hash1) == 64  # SHA-256 hex digest is 64 characters
        assert all(c in "0123456789abcdef" for c in hash1.lower())


async def test_create_api_key(jwt_config, service, session_factory) -> None:
    """Test the creation of an API key."""
    async with transaction(session_factory, requires_new=True, rollback_new=True):
        user_id = "test-user"
        key_id = "test-key"

        # Create an API key
        api_key = await service.create_api_key(user_id, key_id)

        # Check if the plain-text key is returned
        assert isinstance(api_key, str)
        assert len(api_key) == API_KEY_ID_LENGTH + 1 + API_KEY_LENGTH


async def test_validate_api_key_valid(jwt_config, service, session_factory) -> None:
    """Test that a valid API key can be validated."""
    async with transaction(session_factory, requires_new=True, rollback_new=True):
        user_id = "test-user"
        key_id = "test-key"

        # Create API key and get the plain-text key
        api_key = await service.create_api_key(user_id, key_id)

        # Validate the API key
        assert await service.validate_api_key(api_key) == user_id


async def test_validate_api_key_invalid(jwt_config, service, session_factory) -> None:
    """Test that an invalid API key is rejected."""
    async with transaction(session_factory, requires_new=True, rollback_new=True):
        user_id = "test-user"
        key_id = "test-key"

        # Create API key and get the plain-text key
        valid_key = await service.create_api_key(user_id, key_id)

        # Provide an incorrect API key for validation
        invalid_key = "invalid-test-key"

        assert await service.validate_api_key(invalid_key) is None

        # The valid key should still work
        assert await service.validate_api_key(valid_key) == user_id


async def test_revoke_api_key_by_key_id(jwt_config, service, session_factory) -> None:
    """Test that an API key can be revoked by key_id."""
    async with transaction(session_factory, requires_new=True, rollback_new=True):
        user_id = "test-user"
        key_id = "test-key"

        # Create an API key
        await service.create_api_key(user_id, key_id)

        # Revoke the API key
        await service.revoke_api_key(user_id, key_id)

        # Check that the key was removed
        assert all(api_key.key_id != key_id for api_key in await service.list_api_keys(user_id))


async def test_list_api_keys(jwt_config, service, session_factory) -> None:
    """Test that we can list API keys for a given user."""
    async with transaction(session_factory, requires_new=True, rollback_new=True):
        user_id = "user123"

        # Create some API keys for the user
        await service.create_api_key(user_id, "key1")
        await service.create_api_key(user_id, "key2")

        # List the API keys
        keys = await service.list_api_keys(user_id)

        assert keys[0].key_id == "key1"
        assert keys[1].key_id == "key2"
        assert keys[0].created_at is not None
        assert keys[1].created_at is not None

        # Create another key and verify the list updates
        await service.create_api_key(user_id, "key3")
        keys = await service.list_api_keys(user_id)

        assert keys[0].key_id == "key1"
        assert keys[1].key_id == "key2"
        assert keys[2].key_id == "key3"
        assert keys[0].created_at is not None
        assert keys[1].created_at is not None
        assert keys[2].created_at is not None
