"""Repository for the objects table."""

from typing import AsyncIterator, Callable, Sequence

from sqlalchemy import and_, case, delete, func, select

from metadata_backend.api.models import SubmissionWorkflow
from metadata_backend.api.services.accession import generate_accession

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

    async def add_object(self, entity: ObjectEntity, workflow: SubmissionWorkflow) -> str:
        """
        Add a new metadata object entity to the database.

        Args:
            entity: The metadata object entity.
            workflow: The submission workflow.

        Returns:
            The object id used as the primary key value.
        """
        async with transaction(self._session_factory) as session:
            # Generate accession.
            if entity.object_id is None:
                entity.object_id = generate_accession(workflow, entity.object_type)

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
        self,
        submission_id: str,
        object_type: str | Sequence[str] | None = None,
        *,
        object_id: str | None = None,
        name: str | None = None,
    ) -> AsyncIterator[ObjectEntity]:
        """
        Get metadata object entities associated with the given submission.

        The objects are ordered by object type(s) in the given order and by created date.

        Args:
            submission_id: the submission id.
            object_type: filter by object type(s).
            object_id: Object id.
            name: Object name.

        Returns:
            An asynchronous iterator of ordered metadata object entities.
        """

        filters = [ObjectEntity.submission_id == submission_id]
        if object_id is not None:
            filters.append(ObjectEntity.object_id == object_id)
        elif name is not None:
            filters.append(ObjectEntity.name == name)

        order_by = None
        if object_type is not None:
            if isinstance(object_type, str):
                filters.append(ObjectEntity.object_type == object_type)
            else:
                filters.append(ObjectEntity.object_type.in_(object_type))
                order_by = case(
                    {val: idx for idx, val in enumerate(object_type)},
                    value=ObjectEntity.object_type,
                )

        stmt = select(ObjectEntity).where(and_(*filters))

        if order_by is not None:
            stmt = stmt.order_by(order_by, ObjectEntity.created.asc())
        else:
            stmt = stmt.order_by(ObjectEntity.created.asc())

        async with transaction(self._session_factory) as session:
            result = await session.execute(stmt)
            for row in result.scalars():
                yield row

    async def count_objects(self, submission_id: str, object_type: str | None = None) -> int:
        """
        Count metadata object entities associated with the given submission.

        Args:
            submission_id: the submission id.
            object_type: filter by object type.

        Returns:
            The number of matching metadata object entities.
        """

        # Apply filters.
        filters = [ObjectEntity.submission_id == submission_id]
        if object_type is not None:
            filters.append(ObjectEntity.object_type == object_type)

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
