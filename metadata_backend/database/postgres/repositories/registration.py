"""Repository for the registrations table."""

from typing import Callable, Sequence

from sqlalchemy import select

from ..models import RegistrationEntity
from ..repository import session


class RegistrationRepository:
    """Repository for the registrations table."""

    async def add_registration(self, entity: RegistrationEntity) -> str:
        """
        Add a new registration entity to the database.

        Args:
            entity: The registration entity.

        Returns:
            The submission id.
        """
        session().add(entity)
        await session().flush()
        return entity.submission_id

    async def get_registration(self, submission_id: str) -> RegistrationEntity | None:
        """
        Get the registration entity using submission id.

        Args:
            submission_id: The submission id.

        Returns:
            The registration entity.
        """
        stmt = select(RegistrationEntity).where(RegistrationEntity.submission_id == submission_id)
        result = await session().execute(stmt)
        return result.scalar_one_or_none()

    async def get_registrations(self, submission_id: str) -> Sequence[RegistrationEntity]:
        """
        Get all registrations for the submission.

        Args:
            submission_id: The submission id.

        Returns:
            The registrations.
        """
        stmt = select(RegistrationEntity).where(RegistrationEntity.submission_id == submission_id)
        result = await session().execute(stmt)
        return result.scalars().all()

    async def update_registration(
        self, submission_id: str, update_callback: Callable[[RegistrationEntity], None]
    ) -> RegistrationEntity | None:
        """
        Update the registration entity.

        Args:
            submission_id: the submission id.
            update_callback: A coroutine function that updates the registration entity.

        Returns:
            The updated registration entity or None if the registration was not found.
        """
        registration = await self.get_registration(submission_id)
        if registration is None:
            return None
        update_callback(registration)
        return registration
