"""Tests for ingest service."""

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import override
from unittest.mock import AsyncMock, MagicMock

import pytest

from metadata_backend.api.exceptions import ServiceHandlerSystemException, SystemException
from metadata_backend.api.handlers.restapi import RESTAPIServiceHandlers, RESTAPIServices
from metadata_backend.api.models.models import IngestFileState, IngestStatus
from metadata_backend.api.models.sda import (
    CreateDatasetRequest,
    DatasetFile,
    DatasetStatus,
    FileItem,
    IngestFileRequest,
    PostAccessionIdRequest,
)
from metadata_backend.api.models.submission import Submission, SubmissionWorkflow
from metadata_backend.api.processors.xml.bigpicture import get_bp_default_dataset_dir
from metadata_backend.api.services.ingest import SDAIngestService
from metadata_backend.database.postgres.services.dispatch import DispatchKey, DispatchService
from metadata_backend.database.postgres.services.file import FileService
from metadata_backend.database.postgres.services.submission import SubmissionService
from metadata_backend.services.admin_service import AdminServiceHandler
from tests.unit.patches.user import MOCK_USER_ID

_SUBMISSION_ID = "submission"

# The root directory of the imported dataset in SDA. A new submission's root directory is DATASET_{submission id}.
_SDA_ROOT = "ROOT"


def _session_factory_provider():
    return None


def _mock_with_session(service: SDAIngestService):
    async def _with_session(action):
        # As a transaction, an error rolls back the dispatches recorded by the action.
        store = getattr(getattr(service._services, "dispatch", None), "store", None)
        snapshot = dict(store or {})
        try:
            result = action()
            if asyncio.iscoroutine(result):
                return await result
            return result
        except Exception:
            if store is not None:
                store.clear()
                store.update(snapshot)
            raise

    service._with_session = _with_session  # type: ignore[method-assign]


def _ingest_service(
    services: RESTAPIServices | SimpleNamespace, handlers: RESTAPIServiceHandlers | SimpleNamespace, **kwargs
) -> SDAIngestService:
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
            return_value=SimpleNamespace(projectId=MOCK_USER_ID, submissionId=_SUBMISSION_ID, imported=None)
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


def _dispatch_services(dispatched: dict[DispatchKey, datetime] | None = None) -> DispatchService:
    """Build a dispatch service double backed by a plain dict, mirroring DispatchService's shape."""
    store = dict(dispatched or {})

    async def _get_dispatches(_submission_id: str, _service: str):
        return dict(store)

    async def _mark_dispatched(_submission_id: str, _service: str, action: str, target: str = "") -> None:
        store[DispatchKey(action, target)] = datetime.now(timezone.utc)

    async def _clear_dispatches(_submission_id: str, _service: str) -> None:
        store.clear()

    dispatch = MagicMock(spec=DispatchService)
    dispatch.store = store
    dispatch.get_dispatches.side_effect = _get_dispatches
    dispatch.mark_dispatched.side_effect = _mark_dispatched
    dispatch.clear_dispatches.side_effect = _clear_dispatches
    return dispatch


@pytest.mark.asyncio
async def test_sda_ingest_scan_once_processes_candidates_with_worker_bound() -> None:
    """Scanner should process candidate submissions and respect worker limits."""
    services = SimpleNamespace(
        submission=SimpleNamespace(get_submission_ids_for_ingest=AsyncMock(return_value=["s1", "s2", "s3"])),
        file=SimpleNamespace(),
    )
    handlers = SimpleNamespace(admin=AsyncMock())
    service = _ingest_service(services, handlers, scan_interval_seconds=1, max_workers=2)

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
async def test_sda_ingest_scan_once_logs_each_failure_and_waits_for_all_workers(caplog) -> None:
    """A failed submission does not end the scan before the other workers, nor hide their errors."""
    services = SimpleNamespace(
        submission=SimpleNamespace(get_submission_ids_for_ingest=AsyncMock(return_value=["s1", "s2", "s3"])),
        file=SimpleNamespace(),
    )
    handlers = SimpleNamespace(admin=AsyncMock())
    service = _ingest_service(services, handlers, scan_interval_seconds=1, max_workers=3)

    finished: list[str] = []

    async def _ingest_submission_with_session(submission_id: str) -> bool:
        # s1 fails first, and s3 fails after s2 has finished.
        await asyncio.sleep({"s1": 0, "s2": 0.01, "s3": 0.02}[submission_id])
        if submission_id != "s2":
            raise SystemException(f"failure of {submission_id}")
        finished.append(submission_id)
        return True

    service.ingest_submission_with_session = _ingest_submission_with_session  # type: ignore[method-assign]

    with caplog.at_level("ERROR", logger="server"):
        await service.scan_once()

    assert finished == ["s2"]
    errors = [r.getMessage() for r in caplog.records if r.levelname == "ERROR"]
    assert errors == ["Ingest failed for submission s1", "Ingest failed for submission s3"]


@pytest.mark.asyncio
async def test_sda_ingest_skips_when_submission_not_claimed() -> None:
    """Ingest returns False when claim fails (locked or already processed)."""
    services = SimpleNamespace(
        submission=SimpleNamespace(claim_submission_for_ingest=AsyncMock(return_value=None)),
        file=SimpleNamespace(),
    )
    handlers = SimpleNamespace(admin=AsyncMock())
    service = _ingest_service(services, handlers)

    ok = await service.ingest_submission_with_session(_SUBMISSION_ID)
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
    # Not created yet -> create_dataset; registered but not released yet -> release_dataset; then released.
    handlers.admin.get_dataset_status = AsyncMock(side_effect=[None, DatasetStatus.REGISTERED, DatasetStatus.RELEASED])

    service = _ingest_service(services, handlers)

    ok = await service.ingest_submission_with_session(_SUBMISSION_ID)
    assert ok is True
    # Every file is already READY, so there is no inbox status to sync.
    handlers.admin.get_user_files.assert_not_awaited()
    handlers.admin.create_dataset.assert_awaited_once_with(
        CreateDatasetRequest(user=MOCK_USER_ID, accession_ids=["id-a", "id-b"], dataset_id=_SUBMISSION_ID)
    )
    handlers.admin.release_dataset.assert_awaited_once_with(_SUBMISSION_ID)
    services.submission.update_ingested.assert_awaited_once_with(_SUBMISSION_ID)
    # Each successful Admin call is recorded, not just attempted -- this is what the cooldown gate
    # reads back on the next cycle, so it's the actual mechanism this whole feature relies on.
    services.dispatch.mark_dispatched.assert_any_await(_SUBMISSION_ID, "sda_admin", "dataset_create")
    services.dispatch.mark_dispatched.assert_any_await(_SUBMISSION_ID, "sda_admin", "dataset_release")
    # A completed ingest leaves no dispatches rows: the table only ever holds in-flight submissions.
    services.dispatch.clear_dispatches.assert_awaited_once_with(_SUBMISSION_ID, "sda_admin")
    # Dispatches are read once at the start of the cycle, not once per file/action.
    services.dispatch.get_dispatches.assert_awaited_once_with(_SUBMISSION_ID, "sda_admin")


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
    # release_dataset() itself succeeds, but the Admin API still reports the dataset as "registered"
    # (release has not actually taken effect yet).
    handlers.admin.get_dataset_status = AsyncMock(
        side_effect=[None, DatasetStatus.REGISTERED, DatasetStatus.REGISTERED]
    )

    service = _ingest_service(services, handlers)

    ok = await service.ingest_submission_with_session(_SUBMISSION_ID)
    assert ok is False
    handlers.admin.create_dataset.assert_awaited_once()
    handlers.admin.release_dataset.assert_awaited_once_with(_SUBMISSION_ID)
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

    service = _ingest_service(services, handlers)

    ok = await service.ingest_submission_with_session(_SUBMISSION_ID)
    # Only id-b reaches READY where id-a reaches VERIFIED, so not all are READY yet
    assert ok is False

    handlers.admin.ingest_file.assert_awaited_once()
    handlers.admin.post_accession_id.assert_awaited_once()
    services.dispatch.mark_dispatched.assert_any_await(_SUBMISSION_ID, "sda_admin", "file_ingest", "id-a")
    services.dispatch.mark_dispatched.assert_any_await(_SUBMISSION_ID, "sda_admin", "file_accession", "id-b")


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

    service = _ingest_service(services, handlers, retry_cooldown_seconds=3600)

    ok = await service.ingest_submission_with_session(_SUBMISSION_ID)
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

    service = _ingest_service(services, handlers, retry_cooldown_seconds=3600)

    ok = await service.ingest_submission_with_session(_SUBMISSION_ID)
    assert ok is False
    handlers.admin.ingest_file.assert_awaited_once()
    services.dispatch.mark_dispatched.assert_awaited_once_with(_SUBMISSION_ID, "sda_admin", "file_ingest", "id-a")


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
    handlers.admin.get_dataset_status = AsyncMock(return_value=None)

    service = _ingest_service(services, handlers, retry_cooldown_seconds=3600)

    ok = await service.ingest_submission_with_session(_SUBMISSION_ID)
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
    handlers.admin.get_dataset_status = AsyncMock(return_value=DatasetStatus.REGISTERED)

    service = _ingest_service(services, handlers, retry_cooldown_seconds=3600)

    ok = await service.ingest_submission_with_session(_SUBMISSION_ID)
    assert ok is False
    handlers.admin.release_dataset.assert_not_awaited()
    services.dispatch.mark_dispatched.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [DatasetStatus.DEPRECATED, DatasetStatus.FILE_REMOVED])
async def test_sda_ingest_dataset_release_fails_from_status(status: DatasetStatus) -> None:
    """A dataset whose status is not registered or released fails the release without a request to SDA."""
    file_state = IngestFileState(file_id="id-a", path="f1", ingest_status=IngestStatus.READY)
    services = SimpleNamespace(
        submission=_submission_services(), file=_file_services(file_state), dispatch=_dispatch_services()
    )
    handlers = SimpleNamespace(admin=AsyncMock())
    # The dataset was changed in SDA outside SD Submit before its release.
    handlers.admin.get_dataset_status = AsyncMock(return_value=status)

    service = _ingest_service(services, handlers)

    with pytest.raises(SystemException, match=f"can't be released from status '{status.value}'"):
        await service.ingest_submission_with_session(_SUBMISSION_ID)
    handlers.admin.create_dataset.assert_not_awaited()
    handlers.admin.release_dataset.assert_not_awaited()
    services.submission.update_ingested.assert_not_awaited()


@pytest.mark.asyncio
async def test_sda_ingest_keeps_dataset_create_dispatch_when_later_call_fails() -> None:
    """A dataset creation SDA accepted is not requested again within the cooldown when a later call fails."""
    file_state = IngestFileState(file_id="id-a", path="f1", ingest_status=IngestStatus.READY)
    services = SimpleNamespace(
        submission=_submission_services(), file=_file_services(file_state), dispatch=_dispatch_services()
    )
    handlers = SimpleNamespace(admin=AsyncMock())
    # The dataset creation is accepted, but the status check after it fails.
    handlers.admin.get_dataset_status = AsyncMock(side_effect=[None, ServiceHandlerSystemException("sda_admin"), None])

    service = _ingest_service(services, handlers, retry_cooldown_seconds=3600)

    with pytest.raises(ServiceHandlerSystemException):
        await service.ingest_submission_with_session(_SUBMISSION_ID)
    # SDA has not created the dataset yet, and the cooldown has not elapsed.
    assert await service.ingest_submission_with_session(_SUBMISSION_ID) is False
    handlers.admin.create_dataset.assert_awaited_once()


@pytest.mark.asyncio
async def test_sda_ingest_summarises_files_without_admin_status(caplog) -> None:
    """Files the Admin API does not list are logged once in total, not once per file."""
    file_states = [
        IngestFileState(file_id=f"id-{i}", path=f"f{i}", ingest_status=IngestStatus.VERIFIED) for i in range(3)
    ]
    services = SimpleNamespace(submission=_submission_services(), file=_file_services(*file_states))
    handlers = SimpleNamespace(admin=AsyncMock())
    handlers.admin.get_user_files.return_value = [_file_item("f0", "verified")]
    service = _ingest_service(services, handlers)

    with caplog.at_level("INFO", logger="server"):
        await service._sync_file_ingest_states(
            user_id=MOCK_USER_ID,
            submission_id=_SUBMISSION_ID,
            file_states=file_states,
            dataset_dir=get_bp_default_dataset_dir(_SUBMISSION_ID),
        )

    services.file.update_ingest_status.assert_not_awaited()
    messages = [
        r.getMessage() for r in caplog.records if r.levelname == "INFO" and "No Admin API status" in r.getMessage()
    ]
    assert messages == [
        f"No Admin API status for 2 of 3 file(s) in submission {_SUBMISSION_ID}, keeping their current status"
    ]


@pytest.mark.asyncio
async def test_sda_ingest_summarises_file_steps(caplog) -> None:
    """File steps are logged once per submission in total, not once per file."""
    file_states = [
        IngestFileState(file_id="id-1", path="f1", ingest_status=IngestStatus.UPLOADED),
        IngestFileState(file_id="id-2", path="f2", ingest_status=IngestStatus.UPLOADED),
        IngestFileState(file_id="id-3", path="f3", ingest_status=IngestStatus.UPLOADED),
        IngestFileState(file_id="id-4", path="f4", ingest_status=IngestStatus.VERIFIED),
        IngestFileState(file_id="id-5", path="f5", ingest_status=IngestStatus.READY),
    ]
    services = SimpleNamespace(
        submission=_submission_services(),
        file=_file_services(*file_states),
        dispatch=_dispatch_services({DispatchKey("file_ingest", "id-2"): datetime.now(timezone.utc)}),
    )
    handlers = SimpleNamespace(admin=AsyncMock())
    handlers.admin.get_user_files.return_value = [_file_item(f.path, f.ingest_status.value) for f in file_states]

    async def _ingest_file(*, data):
        if data.filepath == "f3":
            raise RuntimeError("Admin API failure")

    handlers.admin.ingest_file = AsyncMock(side_effect=_ingest_file)
    service = _ingest_service(services, handlers, retry_cooldown_seconds=3600)

    with caplog.at_level("INFO", logger="server"):
        assert await service.ingest_submission_with_session(_SUBMISSION_ID) is False

    info = [r.getMessage() for r in caplog.records if r.levelname == "INFO"]
    assert (
        f"Submission {_SUBMISSION_ID} file ingest step: 1 ingest(s) triggered, 1 accession id(s) assigned, "
        "1 awaiting a previous dispatch, 1 failed"
    ) in info
    assert not [m for m in info if "file_id=" in m]


@pytest.mark.asyncio
async def test_sda_ingest_summarises_status_updates(caplog) -> None:
    """Status updates are logged once per submission by transition, and only errors per file."""
    file_states = [
        IngestFileState(file_id="id-1", path="f1", ingest_status=IngestStatus.UPLOADED),
        IngestFileState(file_id="id-2", path="f2", ingest_status=IngestStatus.VERIFIED),
        IngestFileState(file_id="id-3", path="f3", ingest_status=IngestStatus.VERIFIED),
        IngestFileState(file_id="id-4", path="f4", ingest_status=IngestStatus.VERIFIED),
    ]
    services = SimpleNamespace(submission=_submission_services(), file=_file_services(*file_states))
    handlers = SimpleNamespace(admin=AsyncMock())
    handlers.admin.get_user_files.return_value = [
        _file_item("f1", "verified"),
        _file_item("f2", "ready"),
        _file_item("f3", "ready"),
        _file_item("f4", "error"),
    ]
    service = _ingest_service(services, handlers)

    with caplog.at_level("INFO", logger="server"):
        await service._sync_file_ingest_states(
            user_id=MOCK_USER_ID,
            submission_id=_SUBMISSION_ID,
            file_states=file_states,
            dataset_dir=get_bp_default_dataset_dir(_SUBMISSION_ID),
        )

    assert services.file.update_ingest_status.await_count == 4
    info = [r.getMessage() for r in caplog.records if r.levelname == "INFO"]
    assert (
        f"Updated 4 file status(es) in submission {_SUBMISSION_ID}: uploaded -> verified: 1, verified -> error: 1, "
        "verified -> ready: 2"
    ) in info
    assert not [m for m in info if "file_id=" in m]
    warnings = [r.getMessage() for r in caplog.records if r.levelname == "WARNING"]
    assert warnings == [f"Admin API reported an error for submission {_SUBMISSION_ID} file_id=id-4 path=f4"]


@pytest.mark.asyncio
async def test_sda_ingest_logs_start_once(caplog) -> None:
    """The scan that starts ingesting a submission logs it, and so does no scan after it."""
    file_state = IngestFileState(file_id="id-1", path="f1", ingest_status=IngestStatus.UPLOADED)
    services = SimpleNamespace(
        submission=_submission_services(), file=_file_services(file_state), dispatch=_dispatch_services()
    )
    handlers = SimpleNamespace(admin=AsyncMock())
    handlers.admin.get_user_files.return_value = [_file_item("f1", "uploaded")]
    service = _ingest_service(services, handlers, retry_cooldown_seconds=3600)

    with caplog.at_level("INFO", logger="server"):
        await service.ingest_submission_with_session(_SUBMISSION_ID)
        first = [r.getMessage() for r in caplog.records if r.levelname == "INFO"]
        caplog.clear()
        # The first scan recorded its ingest dispatch, so the next one only waits on it.
        await service.ingest_submission_with_session(_SUBMISSION_ID)
        second = [r.getMessage() for r in caplog.records if r.levelname == "INFO"]

    assert f"Starting ingest for submission {_SUBMISSION_ID} with 1 file(s)" in first
    assert second == []


class _MockAdminServiceHandler(AdminServiceHandler):
    """
    A mock SDA Admin API service with one released dataset, for testing how the ingest of an imported submission
    replaces the dataset's metadata XMLs.

    Requests change the inbox and the dataset as the SDA API would, each completing before the next scan: starting
    a file's ingest verifies it, and assigning its accession makes it ready and lets it be added to a dataset.
    Removing a file sets the dataset status to file_removed, adding files sets it to registered, and releasing a
    registered dataset sets it to released. Every request is recorded in calls.

    :param sda_files: The files in the SDA dataset when the test starts, as accession id to path: the data files,
        thumbnails and old metadata XMLs, which were already in SDA. Removing and adding files changes them.
    :param inbox_files: The files in the user's inbox, as path to Admin API file status: the new metadata XMLs,
        written to the inbox at publish.
    :param ignored_removals: How many of the first removal requests are ignored, as SDA may do.
    :param failing_removals: The accession ids whose removal requests fail.
    """

    def __init__(
        self,
        sda_files: dict[str, str],
        *,
        inbox_files: dict[str, str] | None = None,
        ignored_removals: int = 0,
        failing_removals: set[str] | None = None,
    ) -> None:
        # The Admin API configuration and HTTP client of the real handler are not needed.
        self.sda_files = dict(sda_files)
        self.inbox_files = dict(inbox_files or {})
        # The files that have an accession and can be added to a dataset, as accession id to path.
        self.ingested_files: dict[str, str] = {}
        self.status: DatasetStatus | None = DatasetStatus.RELEASED
        self.ignored_removals = ignored_removals
        self.failing_removals = set(failing_removals or ())
        self.calls: list[tuple[str, ...]] = []

    @override
    async def get_user_files(self, username: str, path_prefix: str = "") -> list[FileItem]:
        self.calls.append(("get_user_files", path_prefix))
        return [
            _file_item(path, status) for path, status in self.inbox_files.items() if path.startswith(f"{path_prefix}/")
        ]

    @override
    async def ingest_file(self, *, data: IngestFileRequest | None = None, file_id: str | None = None) -> None:
        assert data is not None
        self.calls.append(("ingest_file", data.filepath))
        self.inbox_files[data.filepath] = IngestStatus.VERIFIED.value

    @override
    async def post_accession_id(
        self, *, data: PostAccessionIdRequest | None = None, file_id: str | None = None, accession_id: str | None = None
    ) -> None:
        assert data is not None
        self.calls.append(("post_accession_id", data.filepath, data.accession_id))
        self.inbox_files[data.filepath] = IngestStatus.READY.value
        self.ingested_files[data.accession_id] = data.filepath

    @override
    async def list_ingested_files(self, _dataset_id: str) -> list[DatasetFile]:
        # The file id of each file is its accession id with a prefix.
        return [
            DatasetFile(id=f"file-{accession_id}", accessionID=accession_id, path=path)
            for accession_id, path in self.sda_files.items()
        ]

    @override
    async def mark_file_removed(self, file_id: str, reason: str) -> None:
        self.calls.append(("mark_file_removed", file_id))

    @override
    async def remove_ingested_file(self, _dataset_id: str, accession_id: str) -> None:
        self.calls.append(("remove_ingested_file", accession_id))
        if accession_id in self.failing_removals:
            raise ServiceHandlerSystemException("sda_admin")
        if self.ignored_removals:
            self.ignored_removals -= 1
            return
        del self.sda_files[accession_id]
        self.status = DatasetStatus.FILE_REMOVED

    @override
    async def create_dataset(self, data: CreateDatasetRequest) -> None:
        self.calls.append(("create_dataset", *data.accession_ids))
        # As in SDA, only files that have been ingested can be added. An unknown accession is a KeyError.
        self.sda_files.update({accession_id: self.ingested_files[accession_id] for accession_id in data.accession_ids})
        self.status = DatasetStatus.REGISTERED

    @override
    async def release_dataset(self, _dataset_id: str) -> None:
        self.calls.append(("release_dataset",))
        if self.status == DatasetStatus.REGISTERED:
            self.status = DatasetStatus.RELEASED

    @override
    async def get_dataset_status(self, _dataset_id: str) -> DatasetStatus | None:
        return self.status


def _imported_services(*file_states: IngestFileState, dispatch: DispatchService) -> RESTAPIServices:
    """Build the services for ingesting an imported submission with the given files."""
    submission = MagicMock(spec=SubmissionService)
    submission.claim_submission_for_ingest.return_value = Submission(
        projectId=MOCK_USER_ID,
        submissionId=_SUBMISSION_ID,
        name="name",
        title="title",
        description="description",
        workflow=SubmissionWorkflow.BP,
        imported=True,
    )
    # The file states change as the ingest updates them.
    states = {state.file_id: state for state in file_states}

    async def _get_ingest_file_states(_submission_id: str) -> list[IngestFileState]:
        return list(states.values())

    async def _update_ingest_status(file_id: str, ingest_status: IngestStatus, **_kwargs: object) -> None:
        states[file_id] = states[file_id].model_copy(update={"ingest_status": ingest_status})

    file = MagicMock(spec=FileService)
    file.get_ingest_file_states.side_effect = _get_ingest_file_states
    file.update_ingest_status.side_effect = _update_ingest_status
    return RESTAPIServices.model_construct(submission=submission, file=file, dispatch=dispatch)


def _ready_file(file_id: str, path: str) -> IngestFileState:
    """Build the state of a file that has already been ingested."""
    return IngestFileState(file_id=file_id, path=path, ingest_status=IngestStatus.READY)


@pytest.mark.asyncio
async def test_sda_ingest_reconciles_imported_dataset() -> None:
    """The new metadata XMLs are ingested, the old ones removed, the new ones added, and the dataset released."""

    # The data file(s) referenced by the XMLs both in the SDA dataset and the import.
    data_file_path = f"{_SDA_ROOT}/IMAGES/IMAGE_1/test.dcm.c4gh"
    dataset_file_path = f"{_SDA_ROOT}/METADATA/dataset.xml.c4gh"

    data_file = _ready_file("data-file-id", data_file_path)
    # The new dataset XML was written to the inbox at publish, at the old one's path, and is not yet ingested.
    new_dataset_xml = IngestFileState(
        file_id="new-dataset-id", path=dataset_file_path, ingest_status=IngestStatus.SUBMITTED
    )
    admin = _MockAdminServiceHandler(
        sda_files={
            "data-file-id": data_file_path,
            "old-dataset-id": dataset_file_path,
        },
        inbox_files={dataset_file_path: IngestStatus.UPLOADED.value},
    )
    services = _imported_services(data_file, new_dataset_xml, dispatch=_dispatch_services())
    service = _ingest_service(services, RESTAPIServiceHandlers.model_construct(admin=admin))

    # First ingest scan: the new XML is listed in the inbox under the dataset's root directory, and ingested.
    assert await service.ingest_submission(_SUBMISSION_ID) is False
    assert admin.calls == [("get_user_files", _SDA_ROOT), ("ingest_file", dataset_file_path)]

    # Second ingest scan: the verified new XML is given its accession.
    assert await service.ingest_submission(_SUBMISSION_ID) is False
    assert admin.calls[2:] == [
        ("get_user_files", _SDA_ROOT),
        ("post_accession_id", dataset_file_path, "new-dataset-id"),
    ]

    # Third ingest scan: the new XML is ready, so the old one is marked removed, so that the inbox does not
    # list it again, and removed from the dataset.
    assert await service.ingest_submission(_SUBMISSION_ID) is False
    assert admin.calls[4:] == [
        ("get_user_files", _SDA_ROOT),
        ("mark_file_removed", "file-old-dataset-id"),
        ("remove_ingested_file", "old-dataset-id"),
    ]

    # Fourth ingest scan: the new XML is added.
    assert await service.ingest_submission(_SUBMISSION_ID) is False
    assert admin.calls[7:] == [("create_dataset", "new-dataset-id")]

    # Fifth ingest scan: the dataset is released.
    assert await service.ingest_submission(_SUBMISSION_ID) is True
    assert admin.calls[8:] == [("release_dataset",)]
    assert set(admin.sda_files) == {"data-file-id", "new-dataset-id"}
    services.submission.update_ingested.assert_awaited_once_with(_SUBMISSION_ID)


@pytest.mark.asyncio
async def test_sda_ingest_retry_removal(caplog) -> None:
    """An Admin API file removal is requested again after its cooldown if it has not taken effect."""

    data_file_path = f"{_SDA_ROOT}/IMAGES/IMAGE_1/test.dcm.c4gh"
    dataset_file_path = f"{_SDA_ROOT}/METADATA/dataset.xml.c4gh"

    data_file = _ready_file("data-file-id", data_file_path)
    # The new dataset XML replaces the old one, so the old one is removed. It is already ingested, so the
    # first scan goes straight to the removal.
    new_dataset_xml = _ready_file("new-dataset-id", dataset_file_path)
    # Admin API ignores the first file removal request.
    admin = _MockAdminServiceHandler(
        sda_files={
            "data-file-id": data_file_path,
            "old-dataset-id": dataset_file_path,
        },
        ignored_removals=1,
    )
    # The new dataset XML is already ingested, as the Admin API needs to add it to the dataset.
    admin.ingested_files["new-dataset-id"] = dataset_file_path
    services = _imported_services(data_file, new_dataset_xml, dispatch=_dispatch_services())
    service = _ingest_service(services, RESTAPIServiceHandlers.model_construct(admin=admin), retry_cooldown_seconds=60)

    assert await service.ingest_submission(_SUBMISSION_ID) is False
    # Within the cooldown the removal is not requested again.
    assert await service.ingest_submission(_SUBMISSION_ID) is False
    assert admin.calls == [("mark_file_removed", "file-old-dataset-id"), ("remove_ingested_file", "old-dataset-id")]

    # Once the cooldown has expired, the removal is requested again, but the file is not marked removed again.
    service._retry_cooldown_seconds = 0
    assert await service.ingest_submission(_SUBMISSION_ID) is False
    # Once the file is removed, its removal is not requested again, and the new XML is added.
    assert await service.ingest_submission(_SUBMISSION_ID) is False
    assert admin.calls == [
        ("mark_file_removed", "file-old-dataset-id"),
        ("remove_ingested_file", "old-dataset-id"),
        ("remove_ingested_file", "old-dataset-id"),
        ("create_dataset", "new-dataset-id"),
    ]
    assert "requesting its removal again" in caplog.text
    assert "old-dataset-id" not in admin.sda_files


@pytest.mark.asyncio
async def test_sda_ingest_keeps_removal_dispatch_when_later_removal_fails() -> None:
    """A file removal SDA accepted is not requested again within the cooldown when a later removal fails."""

    dataset_file_path = f"{_SDA_ROOT}/METADATA/dataset.xml.c4gh"
    policy_file_path = f"{_SDA_ROOT}/METADATA/policy.xml.c4gh"
    # The new XMLs replace the old ones, which are removed in accession order: the dataset XML first. Its removal
    # is accepted but has not taken effect, and the removal of the policy XML fails.
    admin = _MockAdminServiceHandler(
        sda_files={
            "old-dataset-id": dataset_file_path,
            "old-policy-id": policy_file_path,
        },
        ignored_removals=1,
        failing_removals={"old-policy-id"},
    )
    services = _imported_services(
        _ready_file("new-dataset-id", dataset_file_path),
        _ready_file("new-policy-id", policy_file_path),
        dispatch=_dispatch_services(),
    )
    service = _ingest_service(
        services, RESTAPIServiceHandlers.model_construct(admin=admin), retry_cooldown_seconds=3600
    )

    with pytest.raises(ServiceHandlerSystemException):
        await service.ingest_submission_with_session(_SUBMISSION_ID)
    assert admin.calls == [
        ("mark_file_removed", "file-old-dataset-id"),
        ("remove_ingested_file", "old-dataset-id"),
        ("mark_file_removed", "file-old-policy-id"),
        ("remove_ingested_file", "old-policy-id"),
    ]

    # Within the cooldown only the failed removal is requested again.
    admin.failing_removals.clear()
    assert await service.ingest_submission_with_session(_SUBMISSION_ID) is False
    assert admin.calls[4:] == [
        ("mark_file_removed", "file-old-policy-id"),
        ("remove_ingested_file", "old-policy-id"),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "reported"),
    [(None, "unknown"), (DatasetStatus.DEPRECATED, "deprecated"), (DatasetStatus.FILE_REMOVED, "file_removed")],
)
async def test_sda_ingest_imported_dataset_release_fails_from_status(
    status: DatasetStatus | None, reported: str
) -> None:
    """An imported dataset whose status is not registered or released fails the release without a request to SDA."""

    # The dataset already holds the new metadata XMLs, so the ingest goes straight to the release.
    data_file_path = f"{_SDA_ROOT}/IMAGES/IMAGE_1/test.dcm.c4gh"
    dataset_file_path = f"{_SDA_ROOT}/METADATA/dataset.xml.c4gh"
    admin = _MockAdminServiceHandler(
        sda_files={
            "data-file-id": data_file_path,
            "new-dataset-id": dataset_file_path,
        },
    )
    admin.status = status
    services = _imported_services(
        _ready_file("data-file-id", data_file_path),
        _ready_file("new-dataset-id", dataset_file_path),
        dispatch=_dispatch_services(),
    )
    service = _ingest_service(services, RESTAPIServiceHandlers.model_construct(admin=admin))

    with pytest.raises(SystemException, match=f"can't be released from status '{reported}'"):
        await service.ingest_submission(_SUBMISSION_ID)
    assert admin.calls == []
