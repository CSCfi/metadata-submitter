import os
from datetime import datetime, timedelta, timezone
from typing import Iterator
from unittest.mock import patch

import jwt
import pytest
from fastapi import HTTPException
from pydantic import BaseModel, ValidationError
from starlette import status

from metadata_backend.api.services.auth import (
    API_KEY_ID_LENGTH,
    API_KEY_LENGTH,
    JWT_ALGORITHM,
    NBIS_JWT_ALGORITHM,
    AuthService,
)
from metadata_backend.database.postgres.repositories.api_key import ApiKeyRepository
from tests.unit.patches.user import MOCK_USER_ID, MOCK_USER_NAME
from tests.utils import get_test_es256_keypair


class JwtConfig(BaseModel):
    user_id: str
    user_name: str
    expiration: timedelta
    issuer: str
    jwt_secret: str


@pytest.fixture
def jwt_config() -> Iterator[JwtConfig]:
    config = JwtConfig(
        user_id=MOCK_USER_ID,
        user_name=MOCK_USER_NAME,
        expiration=timedelta(minutes=10),
        issuer="SD Submit",
        jwt_secret="mock-secret",
    )
    env_patcher = patch.dict(os.environ, {"JWT_KEY": config.jwt_secret, "JWT_ISSUER": config.issuer})
    env_patcher.start()
    yield config
    env_patcher.stop()


@pytest.fixture
async def service() -> AuthService:
    return AuthService(ApiKeyRepository())


async def test_create_jwt_token_from_userinfo():
    with patch.object(AuthService, "create_jwt_token", lambda user_id, user_name: f"{user_id}:{user_name}"):
        # CSCUserName
        userinfo = {"CSCUserName": "user", "given_name": "Alice", "family_name": "Watcher"}
        token = await AuthService.create_jwt_token_from_userinfo(userinfo)
        assert token == "user:Alice Watcher"

        # remoteUserIdentifier
        userinfo = {"remoteUserIdentifier": "user", "given_name": "Alice", "family_name": ""}
        token = await AuthService.create_jwt_token_from_userinfo(userinfo)
        assert token == "user:Alice"

        # Sub
        userinfo = {"sub": "user"}
        token = await AuthService.create_jwt_token_from_userinfo(userinfo)
        assert token == "user:user"

        # Missing required claims
        userinfo = {"email": "test@example.com"}
        with pytest.raises(HTTPException) as exec_info:
            await AuthService.create_jwt_token_from_userinfo(userinfo)

        assert exec_info.value.status_code == status.HTTP_401_UNAUTHORIZED


def test_create_jwt_token_contains_required_claims(jwt_config) -> None:
    token = AuthService.create_jwt_token(jwt_config.user_id, jwt_config.user_name, jwt_config.expiration)
    decoded = jwt.decode(token, jwt_config.jwt_secret, algorithms=[JWT_ALGORITHM], issuer=jwt_config.issuer)

    assert decoded["sub"] == jwt_config.user_id
    assert decoded["user_name"] == jwt_config.user_name
    assert decoded["iss"] == jwt_config.issuer
    assert "exp" in decoded
    assert "iat" in decoded


def test_read_csc_jwt_token_returns_user_id(jwt_config) -> None:
    # CSC deployment
    token = AuthService.create_jwt_token(jwt_config.user_id, jwt_config.user_name, jwt_config.expiration)
    user_id, user_name = AuthService.validate_jwt_token(token)
    assert user_id == jwt_config.user_id
    assert user_name == jwt_config.user_name


def test_read_nbis_jwt_token_returns_user_id(jwt_config) -> None:
    # NBIS deployment
    mock_nbis_private_key, mock_nbis_public_key = get_test_es256_keypair()
    monkeypatch = patch.dict(
        os.environ,
        {
            "DEPLOYMENT": "NBIS",
            "JWT_KEY": mock_nbis_public_key,
            "JWT_ISSUER": jwt_config.issuer,
        },
    )
    monkeypatch.start()
    payload = {
        "sub": jwt_config.user_id,
        "iss": jwt_config.issuer,
        "exp": datetime.now(timezone.utc) + jwt_config.expiration,
        "iat": datetime.now(timezone.utc),
    }
    token = jwt.encode(payload, mock_nbis_private_key, algorithm=NBIS_JWT_ALGORITHM)
    user_id, user_name = AuthService.validate_jwt_token(token)
    assert user_id == jwt_config.user_id
    assert user_name == jwt_config.user_id
    monkeypatch.stop()


def test_create_jwt_token_missing_secret_raises(jwt_config, monkeypatch) -> None:
    monkeypatch.delenv("JWT_KEY", raising=False)
    with pytest.raises(ValidationError):
        AuthService.create_jwt_token(jwt_config.user_id, jwt_config.user_name, jwt_config.expiration)


def test_read_jwt_token_missing_secret_raises(jwt_config, monkeypatch) -> None:
    token = AuthService.create_jwt_token(jwt_config.user_id, jwt_config.user_name, jwt_config.expiration)
    monkeypatch.delenv("JWT_KEY", raising=False)
    with pytest.raises(ValidationError):
        AuthService.validate_jwt_token(token)


def test_read_invalid_jwt_token_raises(jwt_config) -> None:
    invalid_token = "invalid"
    with pytest.raises(jwt.InvalidTokenError):
        AuthService.validate_jwt_token(invalid_token)


def test_read_expired_jwt_token_raises(jwt_config) -> None:
    expired_token = AuthService.create_jwt_token(jwt_config.user_id, jwt_config.user_name, timedelta(seconds=-1))
    with pytest.raises(jwt.ExpiredSignatureError):
        AuthService.validate_jwt_token(expired_token)


def test_read_wrong_issuer_jwt_token_raises(jwt_config) -> None:
    token = AuthService.create_jwt_token(jwt_config.user_id, jwt_config.user_name, jwt_config.expiration)
    with pytest.raises(jwt.InvalidIssuerError):
        jwt.decode(token, os.getenv("JWT_KEY"), algorithms=["HS256"], issuer="invalid")


async def test_hash_api_key(jwt_config, service) -> None:
    """Test the API key hash algorithm."""
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


async def test_create_api_key(jwt_config, service) -> None:
    """Test the creation of an API key."""
    user_id = "test-user"
    key_id = "test-key"

    # Create an API key
    api_key = await service.create_api_key(user_id, key_id)

    # Check if the plain-text key is returned
    assert isinstance(api_key, str)
    assert len(api_key) == API_KEY_ID_LENGTH + 1 + API_KEY_LENGTH


async def test_validate_api_key_valid(jwt_config, service) -> None:
    """Test that a valid API key can be validated."""
    user_id = "test-user"
    key_id = "test-key"

    # Create API key and get the plain-text key
    api_key = await service.create_api_key(user_id, key_id)

    # Validate the API key
    assert await service.validate_api_key(api_key) == user_id


async def test_validate_api_key_invalid(jwt_config, service) -> None:
    """Test that an invalid API key is rejected."""
    user_id = "test-user"
    key_id = "test-key"

    # Create API key and get the plain-text key
    valid_key = await service.create_api_key(user_id, key_id)

    # Provide an incorrect API key for validation
    invalid_key = "invalid-test-key"

    assert await service.validate_api_key(invalid_key) is None

    # The valid key should still work
    assert await service.validate_api_key(valid_key) == user_id


async def test_revoke_api_key_by_key_id(jwt_config, service) -> None:
    """Test that an API key can be revoked by key_id."""
    user_id = "test-user"
    key_id = "test-key"

    # Create an API key
    await service.create_api_key(user_id, key_id)

    # Revoke the API key
    await service.revoke_api_key(user_id, key_id)

    # Check that the key was removed
    assert all(api_key.key_id != key_id for api_key in await service.list_api_keys(user_id))


async def test_list_api_keys(jwt_config, service) -> None:
    """Test that we can list API keys for a given user."""
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
