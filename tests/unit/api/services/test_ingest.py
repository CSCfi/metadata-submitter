"""Tests for ingest service."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from metadata_backend.api.models.models import IngestFileState, IngestStatus
from metadata_backend.api.models.sda import CreateDatasetRequest, FileItem
from metadata_backend.api.services.ingest import IngestService


def _session_factory_provider():
    return None


def _mock_with_session(service: IngestService):
    async def _with_session(action):
        result = action()
        if asyncio.iscoroutine(result):
            return await result
        return result

    service._with_session = _with_session  # type: ignore[method-assign]


@pytest.mark.asyncio
async def test_scan_once_processes_candidates_with_worker_bound() -> None:
    """Scanner should process candidate submissions and respect worker limits."""
    services = SimpleNamespace(
        submission=SimpleNamespace(
            get_submission_ids_for_ingest=AsyncMock(return_value=["s1", "s2", "s3"]),
            claim_submission_for_ingest=AsyncMock(return_value=None),
        ),
        file=SimpleNamespace(),
    )
    handlers = SimpleNamespace(admin=AsyncMock())
    service = IngestService(
        services,
        handlers,
        session_factory_provider=_session_factory_provider,
        scan_interval_seconds=1,
        max_workers=2,
    )
    _mock_with_session(service)

    active = 0
    peak = 0

    async def _ingest(submission_id: str) -> bool:
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.01)
        active -= 1
        return True

    service.ingest = _ingest  # type: ignore[method-assign]

    await service.scan_once()
    assert peak <= 2


@pytest.mark.asyncio
async def test_ingest_skips_when_submission_not_claimed() -> None:
    """Ingest returns False when claim fails (locked or already processed)."""
    services = SimpleNamespace(
        submission=SimpleNamespace(claim_submission_for_ingest=AsyncMock(return_value=None)),
        file=SimpleNamespace(),
    )
    handlers = SimpleNamespace(admin=AsyncMock())
    service = IngestService(
        services,
        handlers,
        session_factory_provider=_session_factory_provider,
    )
    _mock_with_session(service)

    ok = await service.ingest_submission_with_session("submission-1")
    assert ok is False


@pytest.mark.asyncio
async def test_ingest_marks_submission_ingested() -> None:
    """Ingest should sync statuses and mark submission ingested when all files are ready."""
    file_states = {
        "f1": IngestFileState(file_id="id-a", path="f1", ingest_status=IngestStatus.READY),
        "f2": IngestFileState(file_id="id-b", path="f2", ingest_status=IngestStatus.READY),
    }

    async def _get_ingest_file_states(_submission_id: str):
        return list(file_states.values())

    async def _get_ingest_file_state(file_id: str):
        for state in file_states.values():
            if state.file_id == file_id:
                return state
        raise AssertionError(f"unexpected file_id: {file_id}")

    services = SimpleNamespace(
        submission=SimpleNamespace(
            claim_submission_for_ingest=AsyncMock(
                return_value=SimpleNamespace(bucket="mock_user_test.what", projectId="mock@user@test.what")
            ),
            update_ingested=AsyncMock(),
        ),
        file=SimpleNamespace(
            get_ingest_file_states=_get_ingest_file_states,
            get_ingest_file_state=_get_ingest_file_state,
            update_ingest_status=AsyncMock(),
            get_file_by_path=AsyncMock(
                side_effect=lambda _sid, path: SimpleNamespace(fileId=file_states[path].file_id)
            ),
        ),
    )
    handlers = SimpleNamespace(admin=AsyncMock())
    handlers.admin.get_user_files.return_value = [
        FileItem(
            fileID="12345678-1234-4234-8234-1234567890ab",
            inboxPath="f1",
            fileStatus="ready",
            createAt="2024-01-01T00:00:00Z",
        ),
        FileItem(
            fileID="22345678-1234-4234-8234-1234567890ab",
            inboxPath="f2",
            fileStatus="ready",
            createAt="2024-01-01T00:00:00Z",
        ),
    ]

    service = IngestService(
        services,
        handlers,
        session_factory_provider=_session_factory_provider,
    )
    _mock_with_session(service)

    ok = await service.ingest_submission_with_session("dataset-1")
    assert ok is True
    handlers.admin.create_dataset.assert_awaited_once_with(
        CreateDatasetRequest(user="mock@user@test.what", accession_ids=["id-a", "id-b"], dataset_id="dataset-1")
    )
    handlers.admin.release_dataset.assert_awaited_once_with("dataset-1")
    services.submission.update_ingested.assert_awaited_once_with("dataset-1")


@pytest.mark.asyncio
async def test_ingest_progresses_files_from_uploaded_to_ready() -> None:
    """Ingest should process files and progress them from UPLOADED to VERIFIED and VERIFIED to READY."""
    file_states = {
        "f1": IngestFileState(file_id="id-a", path="f1", ingest_status=IngestStatus.UPLOADED),
        "f2": IngestFileState(file_id="id-b", path="f2", ingest_status=IngestStatus.VERIFIED),
    }

    async def _get_ingest_file_states(_submission_id: str):
        return list(file_states.values())

    async def _get_ingest_file_state(file_id: str):
        for state in file_states.values():
            if state.file_id == file_id:
                return state
        raise AssertionError(f"unexpected file_id: {file_id}")

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
        submission=SimpleNamespace(
            claim_submission_for_ingest=AsyncMock(
                return_value=SimpleNamespace(bucket="mock_user_test.what", projectId="mock@user@test.what")
            ),
            update_ingested=AsyncMock(),
        ),
        file=SimpleNamespace(
            get_ingest_file_states=_get_ingest_file_states,
            get_ingest_file_state=_get_ingest_file_state,
            update_ingest_status=AsyncMock(side_effect=_update_ingest_status),
            get_file_by_path=AsyncMock(
                side_effect=lambda _sid, path: SimpleNamespace(fileId=file_states[path].file_id)
            ),
        ),
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
    handlers.admin.get_user_files.return_value = [
        FileItem(
            fileID="12345678-1234-4234-8234-1234567890ab",
            inboxPath="f1",
            fileStatus="uploaded",
            createAt="2024-01-01T00:00:00Z",
        ),
        FileItem(
            fileID="22345678-1234-4234-8234-1234567890ab",
            inboxPath="f2",
            fileStatus="verified",
            createAt="2024-01-01T00:00:00Z",
        ),
    ]

    service = IngestService(
        services,
        handlers,
        session_factory_provider=_session_factory_provider,
    )
    _mock_with_session(service)

    ok = await service.ingest_submission_with_session("dataset-1")
    # Only id-b reaches READY where id-a reaches VERIFIED, so not all are READY yet
    assert ok is False

    handlers.admin.ingest_file.assert_awaited_once()
    handlers.admin.post_accession_id.assert_awaited_once()
