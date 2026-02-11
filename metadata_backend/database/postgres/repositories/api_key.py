"""Repository for the api_key table."""

from sqlalchemy import delete, select

from ....api.models.models import ApiKey
from ..models import ApiKeyEntity
from ..repository import session


class ApiKeyRepository:
    """Repository for the api_key table."""

    async def add_api_key(self, api_key: ApiKeyEntity) -> None:
        """
        Add a new API key row to the database.

        Args:
            api_key: The API key row.
        """
        session().add(api_key)

    async def get_api_key(self, key_id: str) -> ApiKeyEntity | None:
        """
        Retrieve the API key row for a hashed API key.

        Args:
            key_id: Generated unique key id.

        Returns:
            The API key row or None if the hashed API key was not found.
        """
        stmt = select(ApiKeyEntity).where(ApiKeyEntity.key_id == key_id)
        result = await session().execute(stmt)
        row = result.scalar_one_or_none()
        return row

    async def get_api_keys(self, user_id: str) -> list[ApiKey]:
        """
        Retrieve all API key rows for a given user with the API key ids, hashes and salt masked.

        Args:
            user_id: The user id to filter API keys.

        Returns:
            A list of API key rows for the user with the API API key ids, hashes and salt masked.
        """
        stmt = select(ApiKeyEntity).where(ApiKeyEntity.user_id == user_id)
        result = await session().execute(stmt)
        rows = result.scalars().all()

        api_keys = []
        for row in rows:
            api_keys.append(ApiKey(key_id=row.user_key_id, created_at=row.created_at))
        return api_keys

    async def delete_api_key(self, user_id: str, user_key_id: str) -> None:
        """
        Delete an API key row matching the given user ID and hashed API key.

        Args:
            user_id: The user id whose API key should be deleted.
            user_key_id: The unique key id assigned by the user.
        """
        stmt = delete(ApiKeyEntity).where(ApiKeyEntity.user_id == user_id, ApiKeyEntity.user_key_id == user_key_id)
        await session().execute(stmt)
