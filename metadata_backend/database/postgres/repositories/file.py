"""Repository for the files table."""

from typing import AsyncIterator, Callable, Sequence

from sqlalchemy import delete, func, or_, select

from metadata_backend.api.models import SubmissionWorkflow
from metadata_backend.api.services.accession import generate_file_accession

from ..models import FileEntity, IngestStatus
from ..repository import SessionFactory, transaction


class FileRepository:
    """Repository for the files table."""

    def __init__(self, session_factory: SessionFactory) -> None:
        """
        Initialize the repository with a session factory.

        Args:
            session_factory: A factory that creates async SQLAlchemy sessions.
        """
        self._session_factory = session_factory

    async def add_file(self, entity: FileEntity, workflow: SubmissionWorkflow) -> str:
        """
        Add a new metadata file entity to the database.

        Args:
            entity: The file entity.
            workflow: the submission workflow.
        Returns:
            The file id used as the primary key value.
        """
        async with transaction(self._session_factory) as session:
            # Generate accession.
            if entity.file_id is None:
                entity.file_id = generate_file_accession(workflow)

            session.add(entity)
            await session.flush()
            return entity.file_id

    async def get_file_by_id(self, file_id: str) -> FileEntity | None:
        """
        Get the file entity using file id.

        Args:
            file_id: The file id.

        Returns:
            The file entity.
        """
        async with transaction(self._session_factory) as session:
            stmt = select(FileEntity).where(FileEntity.file_id == file_id)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def get_file_by_path(self, submission_id: str, path: str) -> FileEntity | None:
        """
        Get the file entity using file path.

        Args:
            submission_id: The submission id.
            path: The file path.

        Returns:
            The file entity.
        """
        async with transaction(self._session_factory) as session:
            stmt = select(FileEntity).where(FileEntity.submission_id == submission_id, FileEntity.path == path)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def get_files(
        self, submission_id: str, *, ingest_statuses: Sequence[IngestStatus] | None = None
    ) -> AsyncIterator[FileEntity]:
        """
        Get file entities associated with the submission..

        Args:
            submission_id: the submission id.
            ingest_statuses: filter by ingest statuses.

        Returns:
            Asynchronous interator of file entities.
        """

        # Apply filters.
        filters = []
        if ingest_statuses is not None:
            filters = [FileEntity.ingest_status == ingest_status for ingest_status in ingest_statuses]

        # Select objects.
        if filters:
            stmt = select(FileEntity).where(FileEntity.submission_id == submission_id, or_(*filters))
        else:
            stmt = select(FileEntity).where(FileEntity.submission_id == submission_id)

        async with transaction(self._session_factory) as session:
            result = await session.execute(stmt)
            for row in result.scalars():
                yield row

    async def count_files(self, submission_id: str, *, ingest_statuses: Sequence[IngestStatus] | None = None) -> int:
        """
        Count file entities associated with the submission.

        Args:
            submission_id: the submission id.
            ingest_statuses: filter by ingest statuses.

        Returns:
            The count of matching file entities.
        """

        filters = []
        if ingest_statuses is not None:
            filters = [FileEntity.ingest_status == ingest_status for ingest_status in ingest_statuses]

        if filters:
            stmt = select(func.count()).where(  # pylint: disable=not-callable
                FileEntity.submission_id == submission_id, or_(*filters)
            )
        else:
            stmt = select(func.count()).where(FileEntity.submission_id == submission_id)  # pylint: disable=not-callable

        async with transaction(self._session_factory) as session:
            result = await session.execute(stmt)
            count = result.scalar_one()
            return count

    async def count_bytes(self, submission_id: str) -> int:
        """
        Count file bytes associated with the submission.

        Args:
            submission_id: the submission id.

        Returns:
            The file bytes of matching file entities.
        """

        stmt = select(func.sum(FileEntity.bytes)).where(FileEntity.submission_id == submission_id)

        async with transaction(self._session_factory) as session:
            result = await session.execute(stmt)
            return result.scalar_one()

    async def update_file(self, file_id: str, update_callback: Callable[[FileEntity], None]) -> FileEntity | None:
        """
        Update the file entity.

        Args:
            file_id: the file id.
            update_callback: A coroutine function that updates the file entity.

        Returns:
            The updated file entity or None if the file id was not found.
        """
        async with transaction(self._session_factory):
            file = await self.get_file_by_id(file_id)
            if file is None:
                return None
            update_callback(file)
            return file

    async def delete_file_by_id(self, file_id: str) -> bool:
        """
        Get the file entity using file id.

        Args:
            file_id: The file id.

        Returns:
            True if the file was deleted, False otherwise.
        """
        async with transaction(self._session_factory) as session:
            stmt = delete(FileEntity).where(FileEntity.file_id == file_id)
            result = await session.execute(stmt)
            return result.rowcount > 0

    async def delete_file_by_path(self, submission_id: str, path: str) -> bool:
        """
        Get the file entity using file id.

        Args:
            param submission_id: the submission id
            param path: the file path

        Returns:
            True if the file was deleted, False otherwise.
        """
        async with transaction(self._session_factory) as session:
            stmt = delete(FileEntity).where(FileEntity.submission_id == submission_id, FileEntity.path == path)
            result = await session.execute(stmt)
            return result.rowcount > 0
