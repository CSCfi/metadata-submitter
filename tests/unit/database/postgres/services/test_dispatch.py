"""Test DispatchService."""

from datetime import datetime, timedelta, timezone

from metadata_backend.database.postgres.repositories.submission import SubmissionRepository
from metadata_backend.database.postgres.services.dispatch import DispatchKey, DispatchService, is_due
from tests.unit.database.postgres.helpers import create_submission_entity


async def test_mark_dispatched_with_and_without_target(
    submission_repository: SubmissionRepository, dispatch_service: DispatchService
):
    submission_id = await submission_repository.add_submission(create_submission_entity())

    # Omitting target defaults to "" (a submission-level action), distinct from an explicit
    # file-level target.
    await dispatch_service.mark_dispatched(submission_id, "sda_admin", "dataset_create")
    await dispatch_service.mark_dispatched(submission_id, "sda_admin", "file_ingest", "file-1")

    dispatches = await dispatch_service.get_dispatches(submission_id, "sda_admin")
    assert set(dispatches.keys()) == {DispatchKey("dataset_create", ""), DispatchKey("file_ingest", "file-1")}
    assert all(isinstance(v, datetime) for v in dispatches.values())


async def test_clear_dispatches(submission_repository: SubmissionRepository, dispatch_service: DispatchService):
    submission_id = await submission_repository.add_submission(create_submission_entity())
    await dispatch_service.mark_dispatched(submission_id, "sda_admin", "file_ingest", "file-1")

    await dispatch_service.clear_dispatches(submission_id, "sda_admin")

    assert await dispatch_service.get_dispatches(submission_id, "sda_admin") == {}


def test_is_due_when_never_dispatched():
    assert is_due(None, cooldown_seconds=3600) is True


def test_is_due_within_cooldown():
    dispatched_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    assert is_due(dispatched_at, cooldown_seconds=3600) is False


def test_is_due_after_cooldown_elapses():
    dispatched_at = datetime.now(timezone.utc) - timedelta(hours=2)
    assert is_due(dispatched_at, cooldown_seconds=3600) is True


def test_is_due_normalises_naive_datetime():
    """DateTime(timezone=True) columns round-trip as naive datetimes on SQLite; is_due must not crash."""
    naive_recent = (datetime.now(timezone.utc) - timedelta(minutes=5)).replace(tzinfo=None)
    naive_old = (datetime.now(timezone.utc) - timedelta(hours=2)).replace(tzinfo=None)
    assert is_due(naive_recent, cooldown_seconds=3600) is False
    assert is_due(naive_old, cooldown_seconds=3600) is True
