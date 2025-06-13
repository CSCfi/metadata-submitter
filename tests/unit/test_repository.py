"""Test postgres repositories using sqllite in-memory engine."""

import unittest
import uuid

from metadata_backend.database.postgres.models import ApiKeyEntity
from metadata_backend.database.postgres.repository import ApiKeyRepository, create_engine, create_session_factory


class TestApiKeyRepository(unittest.IsolatedAsyncioTestCase):
    """Test ApiKeyRepository using sqllite in-memory engine."""

    async def asyncSetUp(self) -> None:
        """Set up the test case with an in-memory SQLite database."""
        self.engine = await create_engine()  # pylint: disable=attribute-defined-outside-init
        self.session_factory = create_session_factory(self.engine)  # pylint: disable=attribute-defined-outside-init
        self.repo = ApiKeyRepository(self.session_factory)  # pylint: disable=attribute-defined-outside-init

    async def asyncTearDown(self) -> None:
        """Tear down the test case by disposing of the engine."""
        await self.engine.dispose()

    async def test_add_and_get_api_key(self) -> None:
        """Test adding and retrieving an API key."""
        key_id = f"key_id{str(uuid.uuid4())}"
        user_id = f"user{str(uuid.uuid4())}"
        user_key_id = f"user_key_id{str(uuid.uuid4())}"
        api_key = f"key{str(uuid.uuid4())}"
        salt = f"salt{str(uuid.uuid4())}"

        await self.repo.add_api_key(
            ApiKeyEntity(key_id=key_id, user_id=user_id, user_key_id=user_key_id, api_key=api_key, salt=salt)
        )
        result = await self.repo.get_api_key(key_id)

        self.assertIsNotNone(result)
        self.assertEqual(result.key_id, key_id)
        self.assertEqual(result.user_id, user_id)
        self.assertEqual(result.user_key_id, user_key_id)
        self.assertEqual(result.api_key, api_key)
        self.assertEqual(result.salt, salt)
        self.assertIsNotNone(result.created_at)

    async def test_get_api_keys_masks_api_key(self) -> None:
        """Test that get_api_keys masks the API key and salt."""
        user_id = f"user{str(uuid.uuid4())}"

        # First key.
        key_id = f"key_id{str(uuid.uuid4())}"
        user_key_id = f"user_key_id{str(uuid.uuid4())}"
        api_key = f"key{str(uuid.uuid4())}"
        salt = f"salt{str(uuid.uuid4())}"
        await self.repo.add_api_key(
            ApiKeyEntity(key_id=key_id, user_id=user_id, user_key_id=user_key_id, api_key=api_key, salt=salt)
        )

        # Second key.
        key_id_2 = f"key_id{str(uuid.uuid4())}"
        user_key_id_2 = f"user_key_id{str(uuid.uuid4())}"
        api_key_2 = f"key{str(uuid.uuid4())}"
        salt_2 = f"salt{str(uuid.uuid4())}"
        await self.repo.add_api_key(
            ApiKeyEntity(key_id=key_id_2, user_id=user_id, user_key_id=user_key_id_2, api_key=api_key_2, salt=salt_2)
        )

        results = await self.repo.get_api_keys(user_id)
        self.assertEqual(len(results), 2)

        for row in results:
            self.assertEqual(row.key_id, "")  # masked
            self.assertEqual(row.user_id, user_id)
            self.assertEqual(row.api_key, "")  # masked
            self.assertEqual(row.salt, "")  # masked
            self.assertIsNotNone(row.created_at)

        assert user_key_id in [row.user_key_id for row in results]
        assert user_key_id_2 in [row.user_key_id for row in results]

    async def test_delete_api_key(self) -> None:
        """Test deleting an API key."""
        key_id = f"key_id{str(uuid.uuid4())}"
        user_id = f"user{str(uuid.uuid4())}"
        user_key_id = f"user_key_id{str(uuid.uuid4())}"
        api_key = f"key{str(uuid.uuid4())}"
        salt = f"salt{str(uuid.uuid4())}"

        await self.repo.add_api_key(
            ApiKeyEntity(key_id=key_id, user_id=user_id, user_key_id=user_key_id, api_key=api_key, salt=salt)
        )

        result = await self.repo.get_api_key(key_id)
        self.assertIsNotNone(result)

        await self.repo.delete_api_key(user_id, user_key_id)
        result_after = await self.repo.get_api_key(key_id)
        self.assertIsNone(result_after)

        # Should not raise even if the key doesn't exist.
        await self.repo.delete_api_key(f"user{str(uuid.uuid4())}", f"key{str(uuid.uuid4())}")
