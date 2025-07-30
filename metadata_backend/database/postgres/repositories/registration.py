"""Repository for the registrations table."""

from typing import Callable, Sequence

from sqlalchemy import select

from ..models import RegistrationEntity
from ..repository import SessionFactory, transaction


class RegistrationRepository:
    """Repository for the registrations table."""

    def __init__(self, session_factory: SessionFactory) -> None:
        """
        Initialize the repository with a session factory.

        Args:
            session_factory: A factory that creates async SQLAlchemy sessions.
        """
        self._session_factory = session_factory

    async def add_registration(self, entity: RegistrationEntity) -> str:
        """
        Add a new registration entity to the database.

        Args:
            entity: The registration entity.

        Returns:
            The registration id used as the primary key value.
        """
        async with transaction(self._session_factory) as session:
            session.add(entity)
            await session.flush()
            return entity.registration_id

    async def get_registration_by_id(self, registration_id: str) -> RegistrationEntity | None:
        """
        Get the registration entity using registration id.

        Args:
            registration_id: The registration id.

        Returns:
            The registration entity.
        """
        async with transaction(self._session_factory) as session:
            stmt = select(RegistrationEntity).where(RegistrationEntity.registration_id == registration_id)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def get_registration_by_submission_id(self, submission_id: str) -> RegistrationEntity | None:
        """
        Get the registration entity using submission id.

        Args:
            submission_id: The submission id.

        Returns:
            The registration entity.
        """
        async with transaction(self._session_factory) as session:
            stmt = select(RegistrationEntity).where(
                RegistrationEntity.submission_id == submission_id, RegistrationEntity.object_id.is_(None)
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def get_registration_by_object_id(self, object_id: str) -> RegistrationEntity | None:
        """
        Get the registration entity using object id.

        Args:
            object_id: The object id.

        Returns:
            The registration entity.
        """
        async with transaction(self._session_factory) as session:
            stmt = select(RegistrationEntity).where(RegistrationEntity.object_id == object_id)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def get_registrations(self, submission_id: str) -> Sequence[RegistrationEntity]:
        """
        Get all registrations for the submission.

        Args:
            submission_id: The submission id.

        Returns:
            The registrations.
        """
        async with transaction(self._session_factory) as session:
            stmt = select(RegistrationEntity).where(RegistrationEntity.submission_id == submission_id)
            result = await session.execute(stmt)
            return result.scalars().all()

    async def update_registration(
        self, registration_id: str, update_callback: Callable[[RegistrationEntity], None]
    ) -> RegistrationEntity | None:
        """
        Update the registration entity.

        Args:
            registration_id: the registration id.
            update_callback: A coroutine function that updates the registration entity.

        Returns:
            The updated registration entity or None if the registration id was not found.
        """
        async with transaction(self._session_factory):
            registration = await self.get_registration_by_id(registration_id)
            if registration is None:
                return None
            update_callback(registration)
            return registration
