"""Tests for ingest service."""

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from metadata_backend.api.models.models import IngestFileState, IngestStatus
from metadata_backend.api.models.sda import CreateDatasetRequest, DatasetStatus, FileItem
from metadata_backend.api.services.ingest import SDAIngestService
from metadata_backend.database.postgres.services.dispatch import DispatchKey


def _session_factory_provider():
    return None


def _mock_with_session(service: SDAIngestService):
    async def _with_session(action):
        result = action()
        if asyncio.iscoroutine(result):
            return await result
        return result

    service._with_session = _with_session  # type: ignore[method-assign]


def _build_service(services: SimpleNamespace, handlers: SimpleNamespace, **kwargs) -> SDAIngestService:
    """Construct an SDAIngestService wired to run actions directly, without a real DB session."""
    service = SDAIngestService(services, handlers, session_factory_provider=_session_factory_provider, **kwargs)
    _mock_with_session(service)
    return service


def _file_item(path: str, status: str) -> FileItem:
    """Build a minimal Admin API FileItem for a given inbox path and status."""
    return FileItem(fileID=str(uuid.uuid4()), inboxPath=path, fileStatus=status, createdAt="2024-01-01T00:00:00Z")


def _submission_services() -> SimpleNamespace:
    """Build a submission service double with a single claimable submission."""
    return SimpleNamespace(
        claim_submission_for_ingest=AsyncMock(
            return_value=SimpleNamespace(bucket="mock_user_test.what", projectId="mock@user@test.what")
        ),
        update_ingested=AsyncMock(),
    )


def _file_services(*file_states: IngestFileState) -> SimpleNamespace:
    """Build a file service double serving a fixed list of file states."""

    async def _get_ingest_file_states(_submission_id: str):
        return list(file_states)

    return SimpleNamespace(
        get_ingest_file_states=_get_ingest_file_states,
        update_ingest_status=AsyncMock(),
    )


def _dispatch_services(dispatched: dict[DispatchKey, datetime] | None = None) -> SimpleNamespace:
    """Build a dispatch service double backed by a plain dict, mirroring DispatchService's shape."""
    store = dict(dispatched or {})

    async def _get_dispatches(_submission_id: str, _service: str):
        return dict(store)

    async def _mark_dispatched(_submission_id: str, _service: str, action: str, target: str = "") -> None:
        store[DispatchKey(action, target)] = datetime.now(timezone.utc)

    async def _clear_dispatches(_submission_id: str, _service: str) -> None:
        store.clear()

    return SimpleNamespace(
        get_dispatches=AsyncMock(side_effect=_get_dispatches),
        mark_dispatched=AsyncMock(side_effect=_mark_dispatched),
        clear_dispatches=AsyncMock(side_effect=_clear_dispatches),
    )


@pytest.mark.asyncio
async def test_sda_ingest_scan_once_processes_candidates_with_worker_bound() -> None:
    """Scanner should process candidate submissions and respect worker limits."""
    services = SimpleNamespace(
        submission=SimpleNamespace(get_submission_ids_for_ingest=AsyncMock(return_value=["s1", "s2", "s3"])),
        file=SimpleNamespace(),
    )
    handlers = SimpleNamespace(admin=AsyncMock())
    service = _build_service(services, handlers, scan_interval_seconds=1, max_workers=2)

    active = 0
    peak = 0

    async def _ingest_submission_with_session(submission_id: str) -> bool:
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.01)
        active -= 1
        return True

    # scan_once's semaphore-bounded fan-out calls ingest_submission_with_session per candidate.
    service.ingest_submission_with_session = _ingest_submission_with_session  # type: ignore[method-assign]

    await service.scan_once()
    # 3 candidates with max_workers=2 must overlap up to, but never beyond, the worker bound.
    assert peak == 2


@pytest.mark.asyncio
async def test_sda_ingest_skips_when_submission_not_claimed() -> None:
    """Ingest returns False when claim fails (locked or already processed)."""
    services = SimpleNamespace(
        submission=SimpleNamespace(claim_submission_for_ingest=AsyncMock(return_value=None)),
        file=SimpleNamespace(),
    )
    handlers = SimpleNamespace(admin=AsyncMock())
    service = _build_service(services, handlers)

    ok = await service.ingest_submission_with_session("submission-1")
    assert ok is False


@pytest.mark.asyncio
async def test_sda_ingest_marks_submission_ingested() -> None:
    """Ingest should sync statuses, mark submission ingested, and clear dispatches when all files are ready."""
    file_a = IngestFileState(file_id="id-a", path="f1", ingest_status=IngestStatus.READY)
    file_b = IngestFileState(file_id="id-b", path="f2", ingest_status=IngestStatus.READY)
    services = SimpleNamespace(
        submission=_submission_services(),
        file=_file_services(file_a, file_b),
        dispatch=_dispatch_services(),
    )
    handlers = SimpleNamespace(admin=AsyncMock())
    handlers.admin.get_user_files.return_value = [_file_item("f1", "ready"), _file_item("f2", "ready")]
    # Not created yet -> create_dataset; registered but not released yet -> release_dataset; then released.
    handlers.admin.get_dataset_status = AsyncMock(side_effect=[None, DatasetStatus.REGISTERED, DatasetStatus.RELEASED])

    service = _build_service(services, handlers)

    ok = await service.ingest_submission_with_session("dataset-1")
    assert ok is True
    handlers.admin.create_dataset.assert_awaited_once_with(
        CreateDatasetRequest(user="mock@user@test.what", accession_ids=["id-a", "id-b"], dataset_id="dataset-1")
    )
    handlers.admin.release_dataset.assert_awaited_once_with("dataset-1")
    services.submission.update_ingested.assert_awaited_once_with("dataset-1")
    # Each successful Admin call is recorded, not just attempted -- this is what the cooldown gate
    # reads back on the next cycle, so it's the actual mechanism this whole feature relies on.
    services.dispatch.mark_dispatched.assert_any_await("dataset-1", "sda_admin", "dataset_create")
    services.dispatch.mark_dispatched.assert_any_await("dataset-1", "sda_admin", "dataset_release")
    # A completed ingest leaves no dispatches rows: the table only ever holds in-flight submissions.
    services.dispatch.clear_dispatches.assert_awaited_once_with("dataset-1", "sda_admin")
    # Dispatches are read once at the start of the cycle, not once per file/action.
    services.dispatch.get_dispatches.assert_awaited_once_with("dataset-1", "sda_admin")


@pytest.mark.asyncio
async def test_sda_ingest_does_not_mark_ingested_until_dataset_release_is_confirmed() -> None:
    """Ingest should not mark the submission ingested before the dataset is confirmed as released."""
    file_a = IngestFileState(file_id="id-a", path="f1", ingest_status=IngestStatus.READY)
    file_b = IngestFileState(file_id="id-b", path="f2", ingest_status=IngestStatus.READY)
    services = SimpleNamespace(
        submission=_submission_services(),
        file=_file_services(file_a, file_b),
        dispatch=_dispatch_services(),
    )
    handlers = SimpleNamespace(admin=AsyncMock())
    handlers.admin.get_user_files.return_value = [_file_item("f1", "ready"), _file_item("f2", "ready")]
    # release_dataset() itself succeeds, but the Admin API still reports the dataset as "registered"
    # (release has not actually taken effect yet).
    handlers.admin.get_dataset_status = AsyncMock(
        side_effect=[None, DatasetStatus.REGISTERED, DatasetStatus.REGISTERED]
    )

    service = _build_service(services, handlers)

    ok = await service.ingest_submission_with_session("dataset-1")
    assert ok is False
    handlers.admin.create_dataset.assert_awaited_once()
    handlers.admin.release_dataset.assert_awaited_once_with("dataset-1")
    services.submission.update_ingested.assert_not_awaited()
    services.dispatch.clear_dispatches.assert_not_awaited()


@pytest.mark.asyncio
async def test_sda_ingest_progresses_files_from_uploaded_to_ready() -> None:
    """Ingest should process files and progress them from UPLOADED to VERIFIED and VERIFIED to READY."""
    file_states = {
        "f1": IngestFileState(file_id="id-a", path="f1", ingest_status=IngestStatus.UPLOADED),
        "f2": IngestFileState(file_id="id-b", path="f2", ingest_status=IngestStatus.VERIFIED),
    }

    async def _get_ingest_file_states(_submission_id: str):
        return list(file_states.values())

    async def _update_ingest_status(file_id, ingest_status, *, ingest_error=None, ingest_error_type=None):
        for key, state in file_states.items():
            if state.file_id == file_id:
                file_states[key] = IngestFileState(
                    file_id=state.file_id,
                    path=state.path,
                    ingest_status=ingest_status,
                    ingest_error=ingest_error,
                    ingest_error_type=ingest_error_type,
                    ingest_error_count=state.ingest_error_count,
                )
                return

    services = SimpleNamespace(
        submission=_submission_services(),
        file=SimpleNamespace(
            get_ingest_file_states=_get_ingest_file_states,
            update_ingest_status=AsyncMock(side_effect=_update_ingest_status),
        ),
        dispatch=_dispatch_services(),
    )
    handlers = SimpleNamespace(admin=AsyncMock())

    async def _ingest_file_side_effect(**kwargs):
        # Simulate progression: UPLOADED -> VERIFIED
        await services.file.update_ingest_status("id-a", IngestStatus.VERIFIED)

    async def _post_accession_id_side_effect(**kwargs):
        # Simulate progression: VERIFIED -> READY
        await services.file.update_ingest_status("id-b", IngestStatus.READY)

    handlers.admin.ingest_file = AsyncMock(side_effect=_ingest_file_side_effect)
    handlers.admin.post_accession_id = AsyncMock(side_effect=_post_accession_id_side_effect)

    # Admin API returns files in their current states (no progression yet)
    handlers.admin.get_user_files.return_value = [_file_item("f1", "uploaded"), _file_item("f2", "verified")]

    service = _build_service(services, handlers)

    ok = await service.ingest_submission_with_session("dataset-1")
    # Only id-b reaches READY where id-a reaches VERIFIED, so not all are READY yet
    assert ok is False

    handlers.admin.ingest_file.assert_awaited_once()
    handlers.admin.post_accession_id.assert_awaited_once()
    services.dispatch.mark_dispatched.assert_any_await("dataset-1", "sda_admin", "file_ingest", "id-a")
    services.dispatch.mark_dispatched.assert_any_await("dataset-1", "sda_admin", "file_accession", "id-b")


@pytest.mark.asyncio
async def test_sda_ingest_does_not_redispatch_file_action_within_cooldown() -> None:
    """A file dispatched within the retry cooldown is not re-dispatched even if still pre-action."""
    file_state = IngestFileState(file_id="id-a", path="f1", ingest_status=IngestStatus.UPLOADED)
    dispatched_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    services = SimpleNamespace(
        submission=_submission_services(),
        file=_file_services(file_state),
        dispatch=_dispatch_services({DispatchKey("file_ingest", "id-a"): dispatched_at}),
    )
    handlers = SimpleNamespace(admin=AsyncMock())
    handlers.admin.get_user_files.return_value = [_file_item("f1", "uploaded")]

    service = _build_service(services, handlers, retry_cooldown_seconds=3600)

    ok = await service.ingest_submission_with_session("dataset-1")
    assert ok is False
    handlers.admin.ingest_file.assert_not_awaited()
    services.dispatch.mark_dispatched.assert_not_awaited()


@pytest.mark.asyncio
async def test_sda_ingest_redispatches_file_action_after_cooldown_elapses() -> None:
    """A file dispatched before the retry cooldown elapsed is re-dispatched."""
    file_state = IngestFileState(file_id="id-a", path="f1", ingest_status=IngestStatus.UPLOADED)
    dispatched_at = datetime.now(timezone.utc) - timedelta(hours=2)
    services = SimpleNamespace(
        submission=_submission_services(),
        file=_file_services(file_state),
        dispatch=_dispatch_services({DispatchKey("file_ingest", "id-a"): dispatched_at}),
    )
    handlers = SimpleNamespace(admin=AsyncMock())
    handlers.admin.get_user_files.return_value = [_file_item("f1", "uploaded")]

    service = _build_service(services, handlers, retry_cooldown_seconds=3600)

    ok = await service.ingest_submission_with_session("dataset-1")
    assert ok is False
    handlers.admin.ingest_file.assert_awaited_once()
    services.dispatch.mark_dispatched.assert_awaited_once_with("dataset-1", "sda_admin", "file_ingest", "id-a")


@pytest.mark.asyncio
async def test_sda_ingest_does_not_redispatch_dataset_create_within_cooldown() -> None:
    """Dataset creation dispatched within the retry cooldown is not re-dispatched."""
    file_state = IngestFileState(file_id="id-a", path="f1", ingest_status=IngestStatus.READY)
    dispatched_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    services = SimpleNamespace(
        submission=_submission_services(),
        file=_file_services(file_state),
        dispatch=_dispatch_services({DispatchKey("dataset_create", ""): dispatched_at}),
    )
    handlers = SimpleNamespace(admin=AsyncMock())
    handlers.admin.get_user_files.return_value = [_file_item("f1", "ready")]
    handlers.admin.get_dataset_status = AsyncMock(return_value=None)

    service = _build_service(services, handlers, retry_cooldown_seconds=3600)

    ok = await service.ingest_submission_with_session("dataset-1")
    assert ok is False
    handlers.admin.create_dataset.assert_not_awaited()
    services.dispatch.mark_dispatched.assert_not_awaited()


@pytest.mark.asyncio
async def test_sda_ingest_does_not_redispatch_dataset_release_within_cooldown() -> None:
    """Dataset release dispatched within the retry cooldown is not re-dispatched."""
    file_state = IngestFileState(file_id="id-a", path="f1", ingest_status=IngestStatus.READY)
    dispatched_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    services = SimpleNamespace(
        submission=_submission_services(),
        file=_file_services(file_state),
        dispatch=_dispatch_services({DispatchKey("dataset_release", ""): dispatched_at}),
    )
    handlers = SimpleNamespace(admin=AsyncMock())
    handlers.admin.get_user_files.return_value = [_file_item("f1", "ready")]
    handlers.admin.get_dataset_status = AsyncMock(return_value=DatasetStatus.REGISTERED)

    service = _build_service(services, handlers, retry_cooldown_seconds=3600)

    ok = await service.ingest_submission_with_session("dataset-1")
    assert ok is False
    handlers.admin.release_dataset.assert_not_awaited()
    services.dispatch.mark_dispatched.assert_not_awaited()
