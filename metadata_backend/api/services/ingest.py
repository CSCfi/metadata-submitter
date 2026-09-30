"""Ingest service."""

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import suppress
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ...api.exceptions import ServiceHandlerSystemException
from ...conf.admin import admin_config
from ...database.postgres.repository import _session_context
from ...database.postgres.services.dispatch import DispatchKey, is_due
from ...helpers.logger import LOG
from ..handlers.restapi import RESTAPIServiceHandlers, RESTAPIServices
from ..models.models import IngestErrorType, IngestFileState, IngestStatus
from ..models.sda import CreateDatasetRequest, DatasetStatus, FileItem, IngestFileRequest, PostAccessionIdRequest
from ..models.submission import SubmissionWorkflow

# Dispatch tracking uses the DispatchService (database.postgres.services.dispatch), which treats
# service/action/target as opaque strings — these constants are this module's own vocabulary.
_SDA_ADMIN_SERVICE = "sda_admin"
_ACTION_FILE_INGEST = "file_ingest"
_ACTION_FILE_ACCESSION = "file_accession"
_ACTION_DATASET_CREATE = "dataset_create"
_ACTION_DATASET_RELEASE = "dataset_release"


class IngestService:
    """Background service to ingest files."""

    pass


class SDAIngestService(IngestService):
    """Background service to ingest NeIC SDA files using multiple workers."""

    def __init__(
        self,
        services: RESTAPIServices,
        handlers: RESTAPIServiceHandlers,
        *,
        session_factory_provider: Callable[[], async_sessionmaker[AsyncSession]],
        scan_interval_seconds: int | None = None,
        max_workers: int | None = None,
        retry_cooldown_seconds: int | None = None,
    ) -> None:
        """Initialise the NeIC SDA ingest service.

        :param services: API services
        :param handlers: API handlers
        :param session_factory_provider: Factory to create database sessions.
        :param scan_interval_seconds: Background ingest scanner interval in seconds.
        :param max_workers: Maximum number of concurrent background ingest workers.
        :param retry_cooldown_seconds: Minimum time before re-dispatching an Admin API action.
        """
        admin_handler = handlers.admin
        if admin_handler is None:
            raise RuntimeError("Admin service handler is not configured")

        conf = admin_config()
        self._services = services
        self._admin_handler = admin_handler
        self._session_factory_provider = session_factory_provider
        self._scan_interval_seconds = scan_interval_seconds or conf.INGEST_SCAN_INTERVAL
        self._max_workers = max_workers or conf.INGEST_WORKERS
        self._retry_cooldown_seconds = retry_cooldown_seconds or conf.INGEST_RETRY_COOLDOWN_SECONDS

    async def run_forever(self) -> None:
        """Run the periodic scan loop until the task is cancelled."""
        LOG.info(
            "Starting background ingest scanner (scan_interval_seconds=%s, max_workers=%s)",
            self._scan_interval_seconds,
            self._max_workers,
        )
        while True:
            try:
                await self.scan_once()
            except Exception:
                LOG.exception("Background ingest scan failed")
            await asyncio.sleep(self._scan_interval_seconds)

    async def scan_once(self) -> None:
        """Run one scan cycle.

        This will collect Bigpicture workflow submissions that are published but not yet ingested
        and process them concurrently.
        """
        LOG.info("Starting ingest scan cycle")
        submission_ids: list[str] = await self._with_session(self._get_submission_ids_for_ingest)
        LOG.info("Ingest scan found %s candidate submission(s)", len(submission_ids))
        if not submission_ids:
            LOG.info("Ingest scan cycle finished (no candidates)")
            return

        # Use a semaphore to limit the number of concurrent workers processing submissions.
        sem = asyncio.Semaphore(self._max_workers)

        async def _start(submission_id: str) -> None:
            async with sem:
                await self.ingest_submission_with_session(submission_id)

        await asyncio.gather(*(_start(submission_id) for submission_id in submission_ids))
        LOG.info("Ingest scan cycle finished")

    async def ingest_submission_with_session(self, submission_id: str) -> bool:
        """Attempt to claim and fully process one submission.

        :param submission_id: ID of the submission to process.
        :returns: ``True`` when ingest completed successfully, ``False`` when the submission
            could not be claimed (already processed or locked by another worker) or when ingest
            is still in progress.
        """
        LOG.info("Starting ingest attempt for submission %s", submission_id)
        completed = await self._with_session(lambda: self.ingest_submission(submission_id))
        LOG.info("Finished ingest attempt for submission %s (completed=%s)", submission_id, completed)
        return completed

    async def ingest_submission(self, submission_id: str) -> bool:
        """Drive a single submission through its full ingest lifecycle within an open session.

        Steps performed:
        1. Claim the submission row.
        2. Sync local file statuses with the Admin API to pick up any progress made by a previous run.
        3. Advance each file that is still in progress by issuing the appropriate Admin API call.
        4. If all files have reached ``READY`` status, create and release the dataset and verify
           via the Admin API that the dataset has reached ``released``.
        5. Mark the submission as ingested.

        :param submission_id: ID of the submission to process.
        :returns: ``True`` when ingestion fully completed, ``False`` otherwise.
        """
        # 1. Claim the submission row.
        submission = await self._services.submission.claim_submission_for_ingest(
            submission_id,
            workflow=SubmissionWorkflow.BP,
        )
        if submission is None:
            LOG.info("Submission %s not claimable for ingest (already ingested or locked)", submission_id)
            return False

        files = await self._services.file.get_ingest_file_states(submission_id)
        if not files:
            LOG.info("No files to ingest for submission %s", submission_id)
            return False

        LOG.info("Submission %s has %s file(s) tracked for ingest", submission_id, len(files))

        # Gets all previously recorded dispatches for this submission.
        dispatches = await self._services.dispatch.get_dispatches(submission_id, _SDA_ADMIN_SERVICE)

        # 2. Sync local file statuses with the Admin API to pick up any progress made by a previous run.
        user_id = submission.projectId
        await self._sync_file_ingest_states(user_id=user_id, submission_id=submission_id, file_states=files)

        # 3. Advance each file that is still in progress by issuing the appropriate Admin API call.
        files = await self._services.file.get_ingest_file_states(submission_id)
        for file in files:
            try:
                await self._ingest_file(
                    user_id=user_id,
                    submission_id=submission_id,
                    file=file,
                    dispatches=dispatches,
                )
            except Exception as e:
                LOG.exception(
                    "File ingest step failed for submission %s, file_id=%s, path=%s",
                    submission_id,
                    file.file_id,
                    file.path,
                )
                ingest_error_type = self._classify_admin_error(e)
                await self._services.file.update_ingest_status(
                    file.file_id,
                    IngestStatus.ERROR,
                    ingest_error=str(e),
                    ingest_error_type=ingest_error_type,
                )
                LOG.info(
                    "Marked file as error for submission %s, file_id=%s, error_type=%s",
                    submission_id,
                    file.file_id,
                    ingest_error_type,
                )

        # 4. If all files have reached ``READY`` status, create and release the dataset and verify
        #    via the Admin API that the dataset has reached ``released``.
        all_ready = all(file.ingest_status == IngestStatus.READY for file in files)
        if not all_ready:
            return False

        file_ids = [file.file_id for file in files]
        if not await self._finalize_dataset(
            user_id=user_id, submission_id=submission_id, file_ids=file_ids, dispatches=dispatches
        ):
            return False

        # 5. Mark the submission as ingested.
        # Also clear any dispatch rows for this submission now that ingest is complete.
        await self._services.dispatch.clear_dispatches(submission_id, _SDA_ADMIN_SERVICE)
        await self._services.submission.update_ingested(submission_id)
        LOG.info("Ingest complete for submission %s", submission_id)
        return True

    async def _finalize_dataset(
        self,
        *,
        user_id: str,
        submission_id: str,
        file_ids: list[str],
        dispatches: dict[DispatchKey, datetime],
    ) -> bool:
        """Create, release, and verify the dataset once all of a submission's files are ready.

        :param user_id: ID of the user who owns the submission inbox.
        :param submission_id: the submission id, which matches as the dataset accession ID.
        :param file_ids: accession IDs of the files making up the dataset.
        :param dispatches: dispatches already recorded for this submission, keyed by (action, target).
        :returns: ``True`` once the dataset status reaches ``released``.
        """
        dataset_status = await self._admin_handler.get_dataset_status(submission_id)

        if dataset_status is None:
            # Check if a dispatch is already active without the cooldown having elapsed.
            create_dispatched_at = dispatches.get(DispatchKey(_ACTION_DATASET_CREATE, ""))
            if not is_due(create_dispatched_at, self._retry_cooldown_seconds):
                LOG.debug(
                    "Dataset creation already dispatched for submission %s at %s, cooldown not elapsed",
                    submission_id,
                    create_dispatched_at,
                )
                return False

            LOG.info("Creating dataset for submission %s with %s accession id(s)", submission_id, len(file_ids))
            await self._admin_handler.create_dataset(
                CreateDatasetRequest(user=user_id, accession_ids=file_ids, dataset_id=submission_id)
            )
            await self._services.dispatch.mark_dispatched(submission_id, _SDA_ADMIN_SERVICE, _ACTION_DATASET_CREATE)
            dataset_status = await self._admin_handler.get_dataset_status(submission_id)

        if dataset_status == DatasetStatus.REGISTERED:
            # Check if a dispatch is already active without the cooldown having elapsed.
            release_dispatched_at = dispatches.get(DispatchKey(_ACTION_DATASET_RELEASE, ""))
            if not is_due(release_dispatched_at, self._retry_cooldown_seconds):
                LOG.debug(
                    "Dataset release already dispatched for submission %s at %s, cooldown not elapsed",
                    submission_id,
                    release_dispatched_at,
                )
                return False

            LOG.info("Releasing dataset for submission %s", submission_id)
            await self._admin_handler.release_dataset(submission_id)
            await self._services.dispatch.mark_dispatched(submission_id, _SDA_ADMIN_SERVICE, _ACTION_DATASET_RELEASE)
            dataset_status = await self._admin_handler.get_dataset_status(submission_id)

        if dataset_status != DatasetStatus.RELEASED:
            LOG.info("Dataset for submission %s not yet released (status=%s)", submission_id, dataset_status)
            return False

        return True

    async def _sync_file_ingest_states(
        self,
        *,
        user_id: str,
        submission_id: str,
        file_states: list[IngestFileState],
    ) -> None:
        """Sync file ingest statuses in the DB with the current state reported by the Admin API.

        :param user_id: the user who owns the submission inbox.
        :param submission_id: the submission whose files should be reconciled.
        :param file_states: current file ingest states.
        """
        # Fetch all submission specific files from user's SDA inbox
        inbox_files: list[FileItem] = await self._admin_handler.get_user_files(user_id, submission_id)
        LOG.info(
            "Fetched %s file status(es) from Admin API for submission %s",
            len(inbox_files),
            submission_id,
        )
        admin_status_by_path = {file.inbox_path: file.file_status for file in inbox_files}

        for file in file_states:
            # This is in case the Admin API doesn't have any record of the file yet.
            # In that case we want to keep the existing status in the DB and avoid overwriting it with None.
            admin_status = admin_status_by_path.get(file.path)
            if admin_status is None:
                LOG.info(
                    "No Admin API status for submission %s file_id=%s path=%s yet",
                    submission_id,
                    file.file_id,
                    file.path,
                )
                continue

            parsed_status = self._parse_status(admin_status)
            if parsed_status is None:
                LOG.warning(
                    "Ignoring unknown Admin API status '%s' for submission %s file_id=%s path=%s",
                    admin_status,
                    submission_id,
                    file.file_id,
                    file.path,
                )
                continue

            # Skip no-op updates
            if parsed_status == file.ingest_status:
                continue

            LOG.info(
                "Updating submission %s file_id=%s path=%s status %s -> %s",
                submission_id,
                file.file_id,
                file.path,
                file.ingest_status.value,
                parsed_status.value,
            )

            # Admin-reported error statuses are persisted with a user-error classification.
            if parsed_status == IngestStatus.ERROR:
                await self._services.file.update_ingest_status(
                    file.file_id,
                    IngestStatus.ERROR,
                    ingest_error="Admin API reported fileStatus=error",
                    ingest_error_type=IngestErrorType.USER_ERROR,
                )
            else:
                # Non-error statuses clear any prior ingest error metadata in FileService.
                await self._services.file.update_ingest_status(file.file_id, parsed_status)

    async def _ingest_file(
        self,
        *,
        user_id: str,
        submission_id: str,
        file: IngestFileState,
        dispatches: dict[DispatchKey, datetime],
    ) -> None:
        """Advance a single file by one step along the ingest pipeline.

        :param user_id: the user who owns the submission inbox.
        :param submission_id: the submission the file belongs to.
        :param file: current ingest state loaded for this file in the current cycle.
        :param dispatches: dispatches already recorded for this submission, keyed by (action, target).
        """
        # File status: UPLOADED -> trigger Admin API ingest (file moves toward VERIFIED).
        if file.ingest_status == IngestStatus.UPLOADED:
            # Check if a dispatch is already active without the cooldown having elapsed.
            dispatched_at = dispatches.get(DispatchKey(_ACTION_FILE_INGEST, file.file_id))
            if not is_due(dispatched_at, self._retry_cooldown_seconds):
                LOG.debug(
                    "Ingest already dispatched for submission %s file_id=%s at %s, cooldown not elapsed",
                    submission_id,
                    file.file_id,
                    dispatched_at,
                )
                return

            LOG.info(
                "Triggering ingest for submission %s file_id=%s path=%s",
                submission_id,
                file.file_id,
                file.path,
            )
            await self._admin_handler.ingest_file(data=IngestFileRequest(user=user_id, filepath=file.path))
            await self._services.dispatch.mark_dispatched(
                submission_id, _SDA_ADMIN_SERVICE, _ACTION_FILE_INGEST, file.file_id
            )
            return

        # File status: VERIFIED -> assign the accession ID (file moves toward READY).
        if file.ingest_status == IngestStatus.VERIFIED:
            # Check if a dispatch is already active without the cooldown having elapsed.
            dispatched_at = dispatches.get(DispatchKey(_ACTION_FILE_ACCESSION, file.file_id))
            if not is_due(dispatched_at, self._retry_cooldown_seconds):
                LOG.debug(
                    "Accession dispatch already sent for submission %s file_id=%s at %s, cooldown not elapsed",
                    submission_id,
                    file.file_id,
                    dispatched_at,
                )
                return

            LOG.info(
                "Assigning accession id for submission %s file_id=%s path=%s",
                submission_id,
                file.file_id,
                file.path,
            )
            await self._admin_handler.post_accession_id(
                data=PostAccessionIdRequest(user=user_id, filepath=file.path, accession_id=file.file_id)
            )
            await self._services.dispatch.mark_dispatched(
                submission_id, _SDA_ADMIN_SERVICE, _ACTION_FILE_ACCESSION, file.file_id
            )
            return

    async def _get_submission_ids_for_ingest(self) -> list[str]:
        """Return IDs of all published-but-not-ingested BP submissions."""
        return await self._services.submission.get_submission_ids_for_ingest(workflow=SubmissionWorkflow.BP)

    def _classify_admin_error(self, exc: Exception) -> IngestErrorType:
        """Classify an exception raised by the Admin API into a broad error category.

        ServiceHandlerSystemException indicates an infrastructure problem (e.g. network timeout)
        that may resolve on its own, so it is classified as TRANSIENT_ERROR.

        All other exceptions are treated as PERMANENT_ERROR since they likely indicate a problem with the file
        or its metadata that won't resolve without user intervention.

        :param exc: the exception to classify.
        :returns: the matching :class:`IngestErrorType` member.
        """
        if isinstance(exc, ServiceHandlerSystemException):
            return IngestErrorType.TRANSIENT_ERROR
        return IngestErrorType.PERMANENT_ERROR

    @staticmethod
    def _parse_status(value: str) -> IngestStatus | None:
        """Parse a raw status string from the Admin API response into an IngestStatus member."""
        with suppress(ValueError):
            return IngestStatus(value)
        return None

    async def _with_session[T](self, action: Callable[[], Awaitable[T]]) -> T:
        """Open a new database session and run action inside a transaction."""
        session_factory = self._session_factory_provider()
        async with session_factory() as db_session:
            token = _session_context.set(db_session)
            try:
                async with db_session.begin():
                    return await action()
            finally:
                _session_context.reset(token)
