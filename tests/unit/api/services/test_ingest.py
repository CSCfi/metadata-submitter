"""Tests for ingest service."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from metadata_backend.api.models.sda import CreateDatasetRequest, FileItem, IngestFileRequest, PostAccessionIdRequest
from metadata_backend.api.services.ingest import IngestService
from metadata_backend.database.postgres.models import IngestStatus


class _File:
    def __init__(self, path: str, file_id: str) -> None:
        self.path = path
        self.fileId = file_id


async def _iter_files(files: list[_File]):
    for file in files:
        yield file


@pytest.mark.asyncio
async def test_trigger_ingest_starts_background_workflow_in_order() -> None:
    """Test that ingest workflow is triggered and proceeds in expected order."""
    file_service = SimpleNamespace(
        get_files=lambda *, submission_id: _iter_files([_File("file1", "id-a"), _File("file2", "id-b")]),
        update_ingest_status=AsyncMock(),
    )
    services = SimpleNamespace(file=file_service)
    handlers = SimpleNamespace(admin=AsyncMock())
    # First poll returns all files verified, second poll returns all files ready.
    handlers.admin.get_user_files.side_effect = [
        [
            FileItem(
                fileID="12345678-1234-4234-8234-1234567890ab",
                inboxPath="file1",
                fileStatus="verified",
                createAt="2024-01-01T00:00:00Z",
            ),
            FileItem(
                fileID="22345678-1234-4234-8234-1234567890ab",
                inboxPath="file2",
                fileStatus="verified",
                createAt="2024-01-01T00:00:00Z",
            ),
        ],
        [
            FileItem(
                fileID="12345678-1234-4234-8234-1234567890ab",
                inboxPath="file1",
                fileStatus="ready",
                createAt="2024-01-01T00:00:00Z",
            ),
            FileItem(
                fileID="22345678-1234-4234-8234-1234567890ab",
                inboxPath="file2",
                fileStatus="ready",
                createAt="2024-01-01T00:00:00Z",
            ),
        ],
    ]

    service = IngestService(services, handlers, sleep_seconds=0)
    await service.trigger_ingest(user_id="user1", submission_id="dataset1")

    # Let background task run.
    await asyncio.sleep(0.1)

    # One ingest call per file.
    assert handlers.admin.ingest_file.await_count == 2
    handlers.admin.ingest_file.assert_any_await(data=IngestFileRequest(user="user1", filepath="file1"))
    handlers.admin.ingest_file.assert_any_await(data=IngestFileRequest(user="user1", filepath="file2"))
    handlers.admin.post_accession_id.assert_any_await(
        data=PostAccessionIdRequest(user="user1", filepath="file1", accession_id="id-a")
    )
    handlers.admin.post_accession_id.assert_any_await(
        data=PostAccessionIdRequest(user="user1", filepath="file2", accession_id="id-b")
    )
    # Two files transition through two states: verified and ready.
    assert services.file.update_ingest_status.await_count == 4
    handlers.admin.create_dataset.assert_awaited_once_with(
        CreateDatasetRequest(user="user1", accession_ids=["id-a", "id-b"], dataset_id="dataset1")
    )
    handlers.admin.release_dataset.assert_awaited_once_with("dataset1")


@pytest.mark.asyncio
async def test_trigger_ingest_halts_on_file_error() -> None:
    """Test that if any file reaches error status, workflow should halt and mark all files as error."""
    file_service = SimpleNamespace(
        get_files=lambda *, submission_id: _iter_files([_File("file1", "id-a")]),
        update_ingest_status=AsyncMock(),
    )
    services = SimpleNamespace(file=file_service)
    handlers = SimpleNamespace(admin=AsyncMock())
    # Polling returns an error status, so workflow should stop before dataset operations.
    handlers.admin.get_user_files.return_value = [
        FileItem(
            fileID="12345678-1234-4234-8234-1234567890ab",
            inboxPath="file1",
            fileStatus=IngestStatus.ERROR.value,
            createAt="2024-01-01T00:00:00Z",
        )
    ]

    service = IngestService(services, handlers, sleep_seconds=0)
    await service.trigger_ingest(user_id="user1", submission_id="dataset1")

    await asyncio.sleep(0.1)

    services.file.update_ingest_status.assert_awaited_once_with("id-a", IngestStatus.ERROR)
    handlers.admin.create_dataset.assert_not_awaited()
    handlers.admin.release_dataset.assert_not_awaited()
