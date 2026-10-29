"""Ingest service."""

import asyncio
import logging
from collections import Counter
from collections.abc import Awaitable, Callable
from contextlib import suppress
from datetime import datetime

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ...api.exceptions import ServiceHandlerSystemException, SystemException
from ...conf.admin import admin_config
from ...database.postgres.repository import _session_context
from ...database.postgres.services.dispatch import DispatchKey, is_due
from ...helpers.logger import LOG
from ..handlers.restapi import RESTAPIServiceHandlers, RESTAPIServices
from ..models.models import IngestErrorType, IngestFileState, IngestStatus
from ..models.sda import CreateDatasetRequest, DatasetStatus, FileItem, IngestFileRequest, PostAccessionIdRequest
from ..models.submission import SubmissionWorkflow
from .bigpicture import get_bp_dataset_dir, get_bp_metadata_file_replacements

# Dispatch tracking uses the DispatchService (database.postgres.services.dispatch), which treats
# service/action/target as opaque strings — these constants are this module's own vocabulary.
_SDA_ADMIN_SERVICE = "sda_admin"
_ACTION_FILE_INGEST = "file_ingest"
_ACTION_FILE_ACCESSION = "file_accession"
_ACTION_DATASET_CREATE = "dataset_create"
_ACTION_DATASET_RELEASE = "dataset_release"
_ACTION_DATASET_REMOVE_FILE = "dataset_remove_file"
# File step outcomes besides the dispatched action itself.
_OUTCOME_COOLDOWN = "cooldown"
_OUTCOME_FAILED = "failed"


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
        LOG.debug("Starting ingest scan cycle")
        submission_ids: list[str] = await self._with_session(self._get_submission_ids_for_ingest)
        LOG.debug("Ingest scan found %s candidate submission(s)", len(submission_ids))
        if not submission_ids:
            LOG.debug("Ingest scan cycle finished (no candidates)")
            return

        # Use a semaphore to limit the number of concurrent workers processing submissions.
        sem = asyncio.Semaphore(self._max_workers)

        async def _start(submission_id: str) -> None:
            async with sem:
                # An error is logged here rather than raised, so that the scan waits for every worker
                # and the error of each submission is logged.
                try:
                    await self.ingest_submission_with_session(submission_id)
                except Exception:
                    LOG.exception("Ingest failed for submission %s", submission_id)

        await asyncio.gather(*(_start(submission_id) for submission_id in submission_ids))
        LOG.debug("Ingest scan cycle finished")

    async def ingest_submission_with_session(self, submission_id: str) -> bool:
        """Attempt to claim and fully process one submission.

        An error other than a database error is raised only after the transaction commits, so that the
        dispatch records of the requests SDA accepted before it are kept.

        :param submission_id: ID of the submission to process.
        :returns: ``True`` when ingest completed successfully, ``False`` when the submission
            could not be claimed (already processed or locked by another worker) or when ingest
            is still in progress.
        """
        LOG.debug("Starting ingest attempt for submission %s", submission_id)
        error: Exception | None = None

        async def _ingest() -> bool:
            nonlocal error
            try:
                return await self.ingest_submission(submission_id)
            except SQLAlchemyError:
                # A failed transaction cannot be committed.
                raise
            except Exception as e:
                # Return instead of raising, so that the transaction commits the dispatch records of the
                # requests SDA accepted before the error. The error is raised after the commit. The records
                # can't be written in a separate transaction, because on another connection it would wait
                # for this transaction's lock on the submission.
                error = e
                return False

        completed = await self._with_session(_ingest)
        if error is not None:
            raise error
        LOG.debug("Finished ingest attempt for submission %s (completed=%s)", submission_id, completed)
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
            LOG.debug("Submission %s not claimable for ingest (already ingested or locked)", submission_id)
            return False

        files = await self._services.file.get_ingest_file_states(submission_id)
        if not files:
            LOG.info("No files to ingest for submission %s", submission_id)
            return False

        LOG.debug("Submission %s has %s file(s) tracked for ingest", submission_id, len(files))

        # Gets all previously recorded dispatches for this submission.
        dispatches = await self._services.dispatch.get_dispatches(submission_id, _SDA_ADMIN_SERVICE)
        # Dispatches are recorded from the first Admin API call until ingest completes, so a submission
        # without any is starting ingest. Every later scan logs only the progress it makes.
        if not dispatches:
            LOG.info("Starting ingest for submission %s with %d file(s)", submission_id, len(files))

        # 2. Sync local file statuses with the Admin API to pick up any progress made by a previous run.
        #    Once every file is READY there is no progress left to pick up, and once the dataset is created
        #    the Admin API no longer lists its files, so the sync is skipped while waiting for the release.
        user_id = submission.projectId
        if all(file.ingest_status == IngestStatus.READY for file in files):
            LOG.debug(
                "All %d file(s) of submission %s are ready, skipping Admin API status sync", len(files), submission_id
            )
        else:
            # An imported submission keeps the dataset root directory.
            dataset_dir = get_bp_dataset_dir(submission, (file.path for file in files))
            await self._sync_file_ingest_states(
                user_id=user_id, submission_id=submission_id, file_states=files, dataset_dir=dataset_dir
            )
            # Step 3 reads the statuses the sync just updated.
            files = await self._services.file.get_ingest_file_states(submission_id)

        # 3. Advance each file that is still in progress by issuing the appropriate Admin API call.
        outcomes: Counter[str] = Counter()
        for file in files:
            try:
                outcome = await self._ingest_file(
                    user_id=user_id,
                    submission_id=submission_id,
                    file=file,
                    dispatches=dispatches,
                )
                if outcome:
                    outcomes[outcome] += 1
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
                outcomes[_OUTCOME_FAILED] += 1
                LOG.debug(
                    "Marked file as error for submission %s, file_id=%s, error_type=%s",
                    submission_id,
                    file.file_id,
                    ingest_error_type,
                )

        if outcomes:
            # A scan that only waits on earlier dispatches makes no progress worth logging at info level.
            progressed = outcomes[_ACTION_FILE_INGEST] or outcomes[_ACTION_FILE_ACCESSION] or outcomes[_OUTCOME_FAILED]
            LOG.log(
                logging.INFO if progressed else logging.DEBUG,
                "Submission %s file ingest step: %d ingest(s) triggered, %d accession id(s) assigned, "
                "%d awaiting a previous dispatch, %d failed",
                submission_id,
                outcomes[_ACTION_FILE_INGEST],
                outcomes[_ACTION_FILE_ACCESSION],
                outcomes[_OUTCOME_COOLDOWN],
                outcomes[_OUTCOME_FAILED],
            )

        # 4. If all files have reached ``READY`` status, create and release the dataset and verify
        #    via the Admin API that the dataset has reached ``released``.
        all_ready = all(file.ingest_status == IngestStatus.READY for file in files)
        if not all_ready:
            return False

        file_ids = [file.file_id for file in files]
        if submission.imported:
            if not await self._reconcile_and_finalize_dataset(
                user_id=user_id, submission_id=submission_id, files=files, dispatches=dispatches
            ):
                return False
        elif not await self._finalize_dataset(
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
        :raises SystemException: if the dataset has a status it can't be released from.
        """
        dataset_status = await self._admin_handler.get_dataset_status(submission_id)
        if dataset_status is not None and dataset_status not in (DatasetStatus.REGISTERED, DatasetStatus.RELEASED):
            raise SystemException(
                f"Dataset '{submission_id}' can't be released from status '{dataset_status.value}' in SDA."
            )

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
            LOG.debug("Dataset for submission %s not yet released (status=%s)", submission_id, dataset_status)
            return False

        return True

    async def _reconcile_and_finalize_dataset(
        self,
        *,
        user_id: str,
        submission_id: str,
        files: list[IngestFileState],
        dispatches: dict[DispatchKey, datetime],
    ) -> bool:
        """Replace the old metadata XMLs of an imported dataset with the new ones, and release it.

        Each scan does one step, then returns until the next scan:

        1. Remove the old metadata XMLs from the dataset.
        2. Add the new metadata XMLs to the dataset.
        3. Release the dataset.

        ``get_bp_metadata_file_replacements`` decides which files are added and removed: only the new metadata
        XMLs are added, and only the old ones they replace are removed. Files added to or removed from the
        dataset outside SD Submit after the /import call are left as they are.

        The order matters. SDA only releases a dataset whose status is ``registered``. Removing a file sets
        the status to ``file_removed``, and adding files sets it back to ``registered``. So the removal must
        come before the addition.

        Each scan lists the dataset in SDA to see which step is next. The Admin API accepts a request without
        a guarantee to complete it. So if a request has not taken effect when its cooldown ends, it is sent again.

        :param user_id: ID of the user who owns the submission inbox.
        :param submission_id: the submission ID (dataset accession ID).
        :param files: the submission's files, whose file ids are their accession IDs.
        :param dispatches: dispatches already recorded for this submission, keyed by (action, target).
        :returns: ``True`` once the dataset holds the new metadata XMLs instead of the old ones, and is released.
        """
        sda_files = await self._admin_handler.list_ingested_files(submission_id)
        if sda_files is None:
            raise SystemException(f"Imported dataset '{submission_id}' does not exist in SDA.")

        submission_path_by_accession = {file.file_id: file.path for file in files}
        sda_path_by_accession = {file.accession_id: file.path for file in sda_files}
        sda_file_id_by_accession = {file.accession_id: file.file_id for file in sda_files}

        replacements = get_bp_metadata_file_replacements(submission_path_by_accession, sda_path_by_accession)

        # 1. Remove the old metadata XMLs.
        if replacements.old_accessions:
            for accession_id in replacements.old_accessions:
                dispatched_at = dispatches.get(DispatchKey(_ACTION_DATASET_REMOVE_FILE, accession_id))
                if not is_due(dispatched_at, self._retry_cooldown_seconds):
                    continue
                if dispatched_at is not None:
                    LOG.warning(
                        "File %s is still in imported dataset %s, requesting its removal again",
                        accession_id,
                        submission_id,
                    )
                LOG.info(
                    "Removing file %s (%s) from imported dataset %s",
                    accession_id,
                    sda_path_by_accession[accession_id],
                    submission_id,
                )
                # Removing a file from a dataset leaves the file's own status unchanged, so the inbox of the
                # user who uploaded it would list the old file again. Its file id is listed only while
                # it is in the dataset, so it is marked removed before the first removal request.
                if dispatched_at is None:
                    await self._admin_handler.mark_file_removed(
                        sda_file_id_by_accession[accession_id],
                        f"Replaced by a new file in imported dataset {submission_id}",
                    )
                await self._admin_handler.remove_ingested_file(submission_id, accession_id)
                await self._services.dispatch.mark_dispatched(
                    submission_id, _SDA_ADMIN_SERVICE, _ACTION_DATASET_REMOVE_FILE, accession_id
                )
            return False

        # 2. Add the new metadata XMLs.
        if replacements.new_accessions:
            create_dispatched_at = dispatches.get(DispatchKey(_ACTION_DATASET_CREATE, ""))
            if not is_due(create_dispatched_at, self._retry_cooldown_seconds):
                LOG.debug(
                    "Files already added to imported dataset %s at %s, cooldown not elapsed",
                    submission_id,
                    create_dispatched_at,
                )
                return False

            LOG.info("Adding %d file(s) to imported dataset %s", len(replacements.new_accessions), submission_id)
            await self._admin_handler.create_dataset(
                CreateDatasetRequest(user=user_id, accession_ids=replacements.new_accessions, dataset_id=submission_id)
            )
            await self._services.dispatch.mark_dispatched(submission_id, _SDA_ADMIN_SERVICE, _ACTION_DATASET_CREATE)
            return False

        # 3. Release the dataset.

        # Adding files sets the SDA dataset status to 'registered' and releasing it sets it to
        # 'released'. A SDA file change made outside SD Submit can result in another dataset
        # status. These changes should not happen during the ingest process, are not supported,
        # and are reported here.
        dataset_status = await self._admin_handler.get_dataset_status(submission_id)
        if dataset_status not in (DatasetStatus.REGISTERED, DatasetStatus.RELEASED):
            status = dataset_status.value if dataset_status else "unknown"
            raise SystemException(
                f"Imported dataset '{submission_id}' can't be released from status '{status}' in SDA."
            )

        return await self._finalize_dataset(
            user_id=user_id,
            submission_id=submission_id,
            file_ids=[file.file_id for file in files],
            dispatches=dispatches,
        )

    async def _sync_file_ingest_states(
        self,
        *,
        user_id: str,
        submission_id: str,
        file_states: list[IngestFileState],
        dataset_dir: str,
    ) -> None:
        """Sync file ingest statuses in the DB with the current state reported by the Admin API.

        :param user_id: the user who owns the submission inbox.
        :param submission_id: the submission whose files should be reconciled.
        :param file_states: current file ingest states.
        :param dataset_dir: the root directory of the submission's files.
        """
        # Fetch all submission specific files from user's SDA inbox
        inbox_files: list[FileItem] = await self._admin_handler.get_user_files(user_id, path_prefix=dataset_dir)
        LOG.debug(
            "Fetched %s file status(es) from Admin API for submission %s",
            len(inbox_files),
            submission_id,
        )
        admin_status_by_path = {file.inbox_path: file.file_status for file in inbox_files}

        without_status = 0
        transitions: Counter[str] = Counter()
        for file in file_states:
            # This is in case the Admin API doesn't have any record of the file yet, or no longer lists it
            # because it belongs to a created dataset. In that case we want to keep the existing status in
            # the DB and avoid overwriting it with None.
            admin_status = admin_status_by_path.get(file.path)
            if admin_status is None:
                without_status += 1
                LOG.debug(
                    "No Admin API status for submission %s file_id=%s path=%s",
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

            transitions[f"{file.ingest_status.value} -> {parsed_status.value}"] += 1
            LOG.debug(
                "Updating submission %s file_id=%s path=%s status %s -> %s",
                submission_id,
                file.file_id,
                file.path,
                file.ingest_status.value,
                parsed_status.value,
            )

            # Admin-reported error statuses are persisted with a user-error classification.
            if parsed_status == IngestStatus.ERROR:
                # Each failed file is named, since someone has to act on it.
                LOG.warning(
                    "Admin API reported an error for submission %s file_id=%s path=%s",
                    submission_id,
                    file.file_id,
                    file.path,
                )
                await self._services.file.update_ingest_status(
                    file.file_id,
                    IngestStatus.ERROR,
                    ingest_error="Admin API reported fileStatus=error",
                    ingest_error_type=IngestErrorType.USER_ERROR,
                )
            else:
                # Non-error statuses clear any prior ingest error metadata in FileService.
                await self._services.file.update_ingest_status(file.file_id, parsed_status)

        if transitions:
            LOG.info(
                "Updated %d file status(es) in submission %s: %s",
                transitions.total(),
                submission_id,
                ", ".join(f"{transition}: {count}" for transition, count in sorted(transitions.items())),
            )
        if without_status:
            LOG.info(
                "No Admin API status for %d of %d file(s) in submission %s, keeping their current status",
                without_status,
                len(file_states),
                submission_id,
            )

    async def _ingest_file(
        self,
        *,
        user_id: str,
        submission_id: str,
        file: IngestFileState,
        dispatches: dict[DispatchKey, datetime],
    ) -> str | None:
        """Advance a single file by one step along the ingest pipeline.

        :param user_id: the user who owns the submission inbox.
        :param submission_id: the submission the file belongs to.
        :param file: current ingest state loaded for this file in the current cycle.
        :param dispatches: dispatches already recorded for this submission, keyed by (action, target).
        :returns: the action dispatched, ``_OUTCOME_COOLDOWN`` if one was dispatched too recently to repeat,
            or ``None`` if the file has no step to take.
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
                return _OUTCOME_COOLDOWN

            LOG.debug(
                "Triggering ingest for submission %s file_id=%s path=%s",
                submission_id,
                file.file_id,
                file.path,
            )
            await self._admin_handler.ingest_file(data=IngestFileRequest(user=user_id, filepath=file.path))
            await self._services.dispatch.mark_dispatched(
                submission_id, _SDA_ADMIN_SERVICE, _ACTION_FILE_INGEST, file.file_id
            )
            return _ACTION_FILE_INGEST

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
                return _OUTCOME_COOLDOWN

            LOG.debug(
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
            return _ACTION_FILE_ACCESSION

        return None

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
