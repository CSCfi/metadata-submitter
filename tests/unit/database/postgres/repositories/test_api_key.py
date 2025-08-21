import uuid

import pytest

from metadata_backend.database.postgres.models import ApiKeyEntity
from metadata_backend.database.postgres.repositories.api_key import ApiKeyRepository
from metadata_backend.database.postgres.repository import SessionFactory, transaction


@pytest.fixture
def repo(session_factory) -> ApiKeyRepository:
    return ApiKeyRepository(session_factory)


async def test_add_and_get_api_key(session_factory: SessionFactory, repo: ApiKeyRepository) -> None:
    """Test adding and retrieving an API key."""
    async with transaction(session_factory, requires_new=True, rollback_new=True) as session:
        key_id = f"key_id{str(uuid.uuid4())}"
        user_id = f"user{str(uuid.uuid4())}"
        user_key_id = f"user_key_id{str(uuid.uuid4())}"
        api_key = f"key{str(uuid.uuid4())}"
        salt = f"salt{str(uuid.uuid4())}"

        await repo.add_api_key(
            ApiKeyEntity(key_id=key_id, user_id=user_id, user_key_id=user_key_id, api_key=api_key, salt=salt)
        )
        result = await repo.get_api_key(key_id)

        assert result is not None
        assert result.key_id == key_id
        assert result.user_id == user_id
        assert result.user_key_id == user_key_id
        assert result.api_key == api_key
        assert result.salt == salt
        assert result.created_at is not None


async def test_get_api_keys_masks_api_key(session_factory: SessionFactory, repo: ApiKeyRepository) -> None:
    """Test that get_api_keys masks the API key and salt."""
    async with transaction(session_factory, requires_new=True, rollback_new=True) as session:
        user_id = f"user{str(uuid.uuid4())}"

        # First key.
        key_id = f"key_id{str(uuid.uuid4())}"
        user_key_id = f"user_key_id{str(uuid.uuid4())}"
        api_key = f"key{str(uuid.uuid4())}"
        salt = f"salt{str(uuid.uuid4())}"
        await repo.add_api_key(
            ApiKeyEntity(key_id=key_id, user_id=user_id, user_key_id=user_key_id, api_key=api_key, salt=salt)
        )

        # Second key.
        key_id_2 = f"key_id{str(uuid.uuid4())}"
        user_key_id_2 = f"user_key_id{str(uuid.uuid4())}"
        api_key_2 = f"key{str(uuid.uuid4())}"
        salt_2 = f"salt{str(uuid.uuid4())}"
        await repo.add_api_key(
            ApiKeyEntity(key_id=key_id_2, user_id=user_id, user_key_id=user_key_id_2, api_key=api_key_2, salt=salt_2)
        )

        results = await repo.get_api_keys(user_id)
        assert len(results) == 2

        for row in results:
            assert row.key_id == ""  # masked
            assert row.user_id == user_id
            assert row.api_key == ""  # masked
            assert row.salt == ""  # masked
            assert row.created_at is not None

        assert user_key_id in [row.user_key_id for row in results]
        assert user_key_id_2 in [row.user_key_id for row in results]


async def test_delete_api_key(session_factory: SessionFactory, repo: ApiKeyRepository) -> None:
    """Test deleting an API key."""
    async with transaction(session_factory, requires_new=True, rollback_new=True) as session:
        key_id = f"key_id{str(uuid.uuid4())}"
        user_id = f"user{str(uuid.uuid4())}"
        user_key_id = f"user_key_id{str(uuid.uuid4())}"
        api_key = f"key{str(uuid.uuid4())}"
        salt = f"salt{str(uuid.uuid4())}"

        await repo.add_api_key(
            ApiKeyEntity(key_id=key_id, user_id=user_id, user_key_id=user_key_id, api_key=api_key, salt=salt)
        )

        result = await repo.get_api_key(key_id)
        assert result is not None

        await repo.delete_api_key(user_id, user_key_id)
        result_after = await repo.get_api_key(key_id)
        assert result_after is None

        # Should not raise even if the key doesn't exist.
        await repo.delete_api_key(f"user{str(uuid.uuid4())}", f"key{str(uuid.uuid4())}")
