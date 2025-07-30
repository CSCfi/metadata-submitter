"""Repository for the objects table."""

from typing import AsyncIterator, Callable

from sqlalchemy import and_, delete, func, select

from ..models import ObjectEntity
from ..repository import SessionFactory, transaction


class ObjectRepository:
    """Repository for the objects table."""

    def __init__(self, session_factory: SessionFactory) -> None:
        """
        Initialize the repository with a session factory.

        Args:
            session_factory: A factory that creates async SQLAlchemy sessions.
        """
        self._session_factory = session_factory

    async def add_object(self, entity: ObjectEntity) -> str:
        """
        Add a new metadata object entity to the database.

        Args:
            entity: The metadata object entity.

        Returns:
            The object id used as the primary key value.
        """
        async with transaction(self._session_factory) as session:
            session.add(entity)
            await session.flush()
            return entity.object_id

    async def get_object_by_id(self, object_id: str) -> ObjectEntity | None:
        """
        Get the object entity using object id.

        Args:
            object_id: The object id.

        Returns:
            The object entity.
        """
        async with transaction(self._session_factory) as session:
            stmt = select(ObjectEntity).where(ObjectEntity.object_id == object_id)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def get_object_by_name(self, submission_id: str, name: str) -> ObjectEntity | None:
        """
        Get the object entity using submission id and object name.

        Args:
            submission_id: The submission id.
            name: The name of the object.

        Returns:
            The object entity.
        """
        async with transaction(self._session_factory) as session:
            stmt = select(ObjectEntity).where(ObjectEntity.name == name, ObjectEntity.submission_id == submission_id)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def get_object_by_id_or_name(self, submission_id: str, object_id: str) -> ObjectEntity | None:
        """
        Get the object entity using object id or name.

        Args:
            submission_id: The submission id.
            object_id: The object id or name.

        Returns:
            The object entity.
        """
        entity = await self.get_object_by_id(object_id)
        if entity is None:
            entity = await self.get_object_by_name(submission_id, object_id)

        return entity

    async def get_objects(
        self, submission_id: str, schema: str | None = None, *, is_draft: bool | None = None
    ) -> AsyncIterator[ObjectEntity]:
        """
        Get metadata object entities associated with the given submission.

        Args:
            submission_id: the submission id.
            schema: filter by object schema.
            is_draft: filter by is draft.

        Returns:
            An asynchronous iterator of metadata object entities.
        """

        # Apply filters.
        filters = [ObjectEntity.submission_id == submission_id]
        if schema is not None:
            filters.append(ObjectEntity.schema == schema)
        if is_draft is not None:
            filters.append(ObjectEntity.is_draft == is_draft)

        # Select objects.

        stmt = select(ObjectEntity).where(and_(*filters))

        async with transaction(self._session_factory) as session:
            result = await session.execute(stmt)
            for row in result.scalars():
                yield row

    async def count_objects(
        self, submission_id: str, schema: str | None = None, *, is_draft: bool | None = None
    ) -> int:
        """
        Count metadata object entities associated with the given submission.

        Args:
            submission_id: the submission id.
            schema: filter by object type.
            is_draft: filter by is draft.

        Returns:
            The number of matching metadata object entities.
        """

        # Apply filters.
        filters = [ObjectEntity.submission_id == submission_id]
        if schema is not None:
            filters.append(ObjectEntity.schema == schema)
        if is_draft is not None:
            filters.append(ObjectEntity.is_draft == is_draft)

        stmt = select(func.count()).select_from(ObjectEntity).where(and_(*filters))  # pylint: disable=not-callable

        async with transaction(self._session_factory) as session:
            result = await session.execute(stmt)
            return result.scalar_one()

    async def update_object(
        self, object_id: str, update_callback: Callable[[ObjectEntity], None]
    ) -> ObjectEntity | None:
        """
        Update the metadata object entity.

        Args:
            object_id: the metadata object id.
            update_callback: A coroutine function that updates the metadata object entity.

        Returns:
            The updated object entity or None if the object id was not found.
        """
        async with transaction(self._session_factory):
            obj = await self.get_object_by_id(object_id)
            if obj is None:
                return None
            update_callback(obj)
            return obj

    async def delete_object_by_id(self, object_id: str) -> bool:
        """
        Delete the object entity using object id.

        Args:
            object_id: The object id.

        Returns:
            True if the object was deleted, False otherwise.
        """
        async with transaction(self._session_factory) as session:
            stmt = delete(ObjectEntity).where(ObjectEntity.object_id == object_id)
            result = await session.execute(stmt)
            return result.rowcount > 0

    async def delete_object_by_name(self, submission_id: str, name: str) -> bool:
        """
        Delete the object entity using object name.

        Args:
            submission_id: The submission id.
            name: The object name.

        Returns:
            True if the object was deleted, False otherwise.
        """
        async with transaction(self._session_factory) as session:
            stmt = delete(ObjectEntity).where(ObjectEntity.submission_id == submission_id, ObjectEntity.name == name)
            result = await session.execute(stmt)
            return result.rowcount > 0

    async def delete_object_by_id_or_name(self, submission_id: str, object_id: str) -> bool:
        """
        Delete the object entity using object id or name.

        Args:
            submission_id: The submission id.
            object_id: The object id or name.

        Returns:
            True if the object was deleted, False otherwise.
        """

        deleted = await self.delete_object_by_id(object_id)
        if not deleted:
            deleted = await self.delete_object_by_name(submission_id, object_id)

        return deleted

    async def delete_drafts(self, submission_id: str) -> None:
        """Delete draft metadata objects.

        Args:
            submission_id: the submission id
        """
        async with transaction(self._session_factory):
            async for obj in self.get_objects(submission_id, is_draft=True):
                await self.delete_object_by_id(obj.object_id)
