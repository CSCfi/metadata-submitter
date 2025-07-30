"""Repository for the api_key table."""

from typing import Sequence

from sqlalchemy import delete, select

from ..models import ApiKeyEntity
from ..repository import SessionFactory, transaction


class ApiKeyRepository:
    """Repository for the api_key table."""

    def __init__(self, session_factory: SessionFactory) -> None:
        """
        Initialize the repository with a session factory.

        Args:
            session_factory: A factory that creates async SQLAlchemy sessions.
        """
        self._session_factory = session_factory

    async def add_api_key(self, api_key: ApiKeyEntity) -> None:
        """
        Add a new API key row to the database.

        Args:
            api_key: The API key row.
        """
        async with transaction(self._session_factory) as session:
            session.add(api_key)

    async def get_api_key(self, key_id: str) -> ApiKeyEntity | None:
        """
        Retrieve the API key row for a hashed API key.

        Args:
            key_id: Generated unique key id.

        Returns:
            The API key row or None if the hashed API key was not found.
        """
        async with transaction(self._session_factory) as session:
            stmt = select(ApiKeyEntity).where(ApiKeyEntity.key_id == key_id)
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()
            return row

    async def get_api_keys(self, user_id: str) -> Sequence[ApiKeyEntity]:
        """
        Retrieve all API key rows for a given user with the API key ids, hashes and salt masked.

        Args:
            user_id: The user id to filter API keys.

        Returns:
            A list of API key rows for the user with the API API key ids, hashes and salt masked.
        """
        async with transaction(self._session_factory) as session:
            stmt = select(ApiKeyEntity).where(ApiKeyEntity.user_id == user_id)
            result = await session.execute(stmt)
            rows = result.scalars().all()
            for row in rows:
                row.key_id = ""
                row.api_key = ""
                row.salt = ""
            return rows

    async def delete_api_key(self, user_id: str, user_key_id: str) -> None:
        """
        Delete an API key row matching the given user ID and hashed API key.

        Args:
            user_id: The user id whose API key should be deleted.
            user_key_id: The unique key id assigned by the user.
        """
        async with transaction(self._session_factory) as session:
            stmt = delete(ApiKeyEntity).where(ApiKeyEntity.user_id == user_id, ApiKeyEntity.user_key_id == user_key_id)
            await session.execute(stmt)
