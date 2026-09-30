"""Service for dispatch tracking."""

from datetime import datetime, timedelta, timezone
from typing import NamedTuple

from ..repositories.dispatch import DispatchRepository


class DispatchKey(NamedTuple):
    """Identifies a dispatched action: its action name, and the id of what it applies to.

    ``target`` is "" for a submission-level action (e.g. a dataset create/release), or the id of
    the action's target (e.g. a file id) otherwise.
    """

    action: str
    target: str


def is_due(dispatched_at: datetime | None, cooldown_seconds: int) -> bool:
    """Whether an action may be (re-)dispatched.

    An action is due if it was never dispatched, or if the cooldown has elapsed since it was
    last dispatched without any observed progress (a signal the original message may have been
    lost).

    :param dispatched_at: when the action was last dispatched, if ever.
    :param cooldown_seconds: minimum time to wait before allowing a re-dispatch.
    :returns: ``True`` if the action may be dispatched now.
    """
    if dispatched_at is None:
        return True
    # DateTime(timezone=True) columns round-trip as naive datetimes on SQLite (used in unit
    # tests), even though Postgres returns aware ones; normalise before comparing.
    if dispatched_at.tzinfo is None:
        dispatched_at = dispatched_at.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - dispatched_at) >= timedelta(seconds=cooldown_seconds)


class DispatchService:
    """Service for tracking dispatched external service actions."""

    def __init__(self, repository: DispatchRepository) -> None:
        """Initialize the service."""
        self.__repository = repository

    async def get_dispatches(self, submission_id: str, service: str) -> dict[DispatchKey, datetime]:
        """
        Get dispatch timestamps for a submission and service, keyed by DispatchKey.

        Args:
            submission_id: The submission id.
            service: The external service name.

        Returns:
            The dispatched_at timestamps, keyed by DispatchKey.
        """
        entities = await self.__repository.get_dispatches(submission_id, service)
        return {DispatchKey(entity.action, entity.target): entity.dispatched_at for entity in entities}

    async def mark_dispatched(self, submission_id: str, service: str, action: str, target: str = "") -> None:
        """
        Record that an action was just dispatched.

        Args:
            submission_id: The submission id.
            service: The external service name.
            action: The dispatched action.
            target: The id of what the action applies to, or "" for a submission-level action.
        """
        await self.__repository.mark_dispatched(submission_id, service, action, target)

    async def clear_dispatches(self, submission_id: str, service: str) -> None:
        """
        Clear all dispatch rows for a submission and service.

        Args:
            submission_id: The submission id.
            service: The external service name.
        """
        await self.__repository.delete_dispatches(submission_id, service)
