"""Repository for the dispatches table."""

from datetime import datetime, timezone

from sqlalchemy import delete, select

from ..models import DispatchEntity
from ..repository import session


class DispatchRepository:
    """Repository for the dispatches table."""

    async def get_dispatches(self, submission_id: str, service: str) -> list[DispatchEntity]:
        """Get all dispatch rows for a submission and service.

        Args:
            submission_id: The submission id.
            service: The external service name.

        Returns:
            The matching dispatch rows.
        """
        stmt = select(DispatchEntity).where(
            DispatchEntity.submission_id == submission_id, DispatchEntity.service == service
        )
        result = await session().execute(stmt)
        return list(result.scalars())

    async def mark_dispatched(self, submission_id: str, service: str, action: str, target: str) -> None:
        """Record a dispatch attempt, inserting a new row or updating an existing one.

        Args:
            submission_id: The submission id.
            service: The external service name.
            action: The dispatched action.
            target: The id of what the action applies to, or "" for a submission-level action.
        """
        # Row order matched by name, not position, so a mismatched composite key cannot silently
        # miss an existing row and insert a duplicate later.
        dispatch = await session().get(
            DispatchEntity,
            {"submission_id": submission_id, "service": service, "action": action, "target": target},
        )

        now = datetime.now(timezone.utc)
        if dispatch is None:
            session().add(
                DispatchEntity(
                    submission_id=submission_id,
                    service=service,
                    action=action,
                    target=target,
                    dispatched_at=now,
                    attempts=1,
                )
            )
            return

        dispatch.dispatched_at = now
        dispatch.attempts += 1

    async def delete_dispatches(self, submission_id: str, service: str) -> None:
        """Delete all dispatch rows for a submission and service.

        Args:
            submission_id: The submission id.
            service: The external service name.
        """
        stmt = delete(DispatchEntity).where(
            DispatchEntity.submission_id == submission_id, DispatchEntity.service == service
        )
        await session().execute(stmt)
