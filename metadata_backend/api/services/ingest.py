"""Ingest service."""

import asyncio

from pydantic import BaseModel

from ...database.postgres.models import IngestStatus
from ...helpers.logger import LOG
from ..handlers.restapi import RESTAPIServiceHandlers, RESTAPIServices
from ..models.sda import CreateDatasetRequest, FileItem, IngestFileRequest, PostAccessionIdRequest


class IngestFile(BaseModel):
    """File metadata required by ingest orchestration."""

    path: str
    file_id: str


class IngestService:
    """Service that triggers and completes ingest workflow for Bigpicture submissions in the background."""

    def __init__(
        self,
        services: RESTAPIServices,
        handlers: RESTAPIServiceHandlers,
        *,
        sleep_seconds: float = 30,
    ) -> None:
        """Create ingest service.

        :param services: API services container.
        :param handlers: API service handlers container.
        :param sleep_seconds: Number of seconds to sleep between polling iterations.
        """
        admin_handler = handlers.admin
        if admin_handler is None:
            raise RuntimeError("Admin service handler is not configured")

        self._services = services
        self._handlers = handlers
        self._admin_handler = admin_handler
        self._sleep_seconds = sleep_seconds
        self._tasks: set[asyncio.Task[None]] = set()

    async def trigger_ingest(self, *, user_id: str, submission_id: str) -> None:
        """Start file ingest immediately and schedule completion in a background task.

        :param user_id: User ID of the submission owner.
        :param submission_id: Submission ID (equal to dataset accession ID).
        """
        files = [
            IngestFile(path=file.path, file_id=file.fileId)
            async for file in self._services.file.get_files(submission_id=submission_id)
        ]
        if not files:
            LOG.info("No files to ingest for submission %s", submission_id)
            return

        file_ids: list[str] = []
        tracked_files: dict[str, str] = {}
        for ingest_file in files:
            await self._admin_handler.ingest_file(data=IngestFileRequest(user=user_id, filepath=ingest_file.path))
            file_ids.append(ingest_file.file_id)
            tracked_files[ingest_file.path] = ingest_file.file_id

        task = asyncio.create_task(
            self._run_ingest_workflow(
                user_id=user_id,
                submission_id=submission_id,
                tracked_files=tracked_files,
                file_ids=file_ids,
            )
        )
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _run_ingest_workflow(
        self,
        *,
        user_id: str,
        submission_id: str,
        tracked_files: dict[str, str],
        file_ids: list[str],
    ) -> None:
        """Complete ingest workflow in ordered phases."""
        try:
            await self._poll_until_status(
                user_id=user_id, submission_id=submission_id, files=tracked_files, status=IngestStatus.VERIFIED
            )
            await self._poll_until_status(
                user_id=user_id, submission_id=submission_id, files=tracked_files, status=IngestStatus.READY
            )
            await self._create_and_release_dataset(user_id=user_id, submission_id=submission_id, file_ids=file_ids)
            LOG.info("Background ingest workflow finished for submission %s", submission_id)
        except Exception:
            LOG.exception("Background ingest workflow failed for submission %s", submission_id)

    async def _poll_until_status(
        self,
        *,
        user_id: str,
        submission_id: str,
        files: dict[str, str],
        status: IngestStatus,
    ) -> None:
        """Poll admin API until all tracked files reach the given status."""
        status_found = {file_path: False for file_path in files}
        file_service = self._services.file

        while not all(status_found.values()):
            inbox_files: list[FileItem] = await self._admin_handler.get_user_files(user_id, submission_id)
            for inbox_file in inbox_files:
                inbox_path = inbox_file.inbox_path
                file_status = inbox_file.file_status
                if inbox_path not in status_found or status_found[inbox_path]:
                    continue

                file_id = files[inbox_path]
                if file_status == status.value:
                    status_found[inbox_path] = True
                    await file_service.update_ingest_status(file_id, status)
                    if status == IngestStatus.VERIFIED:
                        await self._admin_handler.post_accession_id(
                            data=PostAccessionIdRequest(user=user_id, filepath=inbox_path, accession_id=file_id)
                        )
                elif file_status == IngestStatus.ERROR.value:
                    await file_service.update_ingest_status(file_id, IngestStatus.ERROR)
                    raise RuntimeError(
                        f"File {inbox_path} in submission {submission_id} has status {IngestStatus.ERROR.value}"
                    )

            if not all(status_found.values()):
                num_waiting = sum(not reached for reached in status_found.values())
                LOG.debug(
                    "%d files were not yet %s for submission %s",
                    num_waiting,
                    status.value,
                    submission_id,
                )
                await asyncio.sleep(self._sleep_seconds)

    async def _create_and_release_dataset(self, *, user_id: str, submission_id: str, file_ids: list[str]) -> None:
        """Create and release dataset once all files are ready."""
        await self._admin_handler.create_dataset(
            CreateDatasetRequest(user=user_id, accession_ids=file_ids, dataset_id=submission_id)
        )
        await self._admin_handler.release_dataset(submission_id)
