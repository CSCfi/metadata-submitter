"""Repository for the submissions table."""

import datetime
import enum
from typing import Awaitable, Callable, Sequence

from sqlalchemy import and_, delete, func, select

from metadata_backend.api.models.submission import Submission
from metadata_backend.api.services.accession import generate_submission_accession

from ..models import SubmissionEntity
from ..repository import SessionFactory, transaction

SUB_FIELD_METADATA = "metadata"
SUB_FIELD_REMS = "rems"
SUB_FIELD_BUCKET = "bucket"


class SubmissionSort(enum.Enum):
    """Submission sorting options."""

    CREATED_DESC = SubmissionEntity.created.desc()
    MODIFIED_DESC = SubmissionEntity.modified.desc()


class SubmissionRepository:
    """Repository for the submissions table."""

    def __init__(self, session_factory: SessionFactory) -> None:
        """
        Initialize the repository with a session factory.

        Args:
            session_factory: A factory that creates async SQLAlchemy sessions.
        """
        self._session_factory = session_factory

    async def add_submission(self, entity: SubmissionEntity) -> str:
        """
        Add a new submission entity to the database.

        Args:
            entity: The submission entity.

        Returns:
            The submission id used as the primary key value.
        """
        async with transaction(self._session_factory) as session:
            # Validate submission document.
            Submission.model_validate(entity.document)

            # Generate accession.
            if entity.submission_id is None:
                entity.submission_id = generate_submission_accession(entity.workflow)

            session.add(entity)
            await session.flush()
            return entity.submission_id

    async def get_submission_by_id(self, submission_id: str) -> SubmissionEntity | None:
        """
        Get the submission entity using submission id.

        Args:
            submission_id: The submission id.

        Returns:
            The submission entity.
        """
        async with transaction(self._session_factory) as session:
            stmt = select(SubmissionEntity).where(SubmissionEntity.submission_id == submission_id)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def get_submission_by_name(self, project_id: str, name: str) -> SubmissionEntity | None:
        """
        Get the submission entity using project id and submission name.

        Args:
            project_id: The project_id.
            name: The name of the submission.

        Returns:
            The submission entity.
        """
        async with transaction(self._session_factory) as session:
            stmt = select(SubmissionEntity).where(
                SubmissionEntity.name == name, SubmissionEntity.project_id == project_id
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def get_submission_by_id_or_name(self, project_id: str, submission_id: str) -> SubmissionEntity | None:
        """
        Get the submission entity using submission id or name.

        Args:
            project_id: The project_id.
            submission_id: The submission id or name.

        Returns:
            The submission entity.
        """
        submission = await self.get_submission_by_id(submission_id)
        if submission is None:
            submission = await self.get_submission_by_name(project_id, submission_id)

        return submission

    async def get_submissions(
        self,
        project_id: str,
        *,
        name: str | None = None,
        is_published: bool | None = None,
        is_ingested: bool | None = None,
        created_start: datetime.datetime | None = None,
        created_end: datetime.datetime | None = None,
        modified_start: datetime.datetime | None = None,
        modified_end: datetime.datetime | None = None,
        sort: SubmissionSort = SubmissionSort.CREATED_DESC,
        page: int | None = None,
        page_size: int | None = None,
    ) -> tuple[Sequence[SubmissionEntity], int]:
        """
        Get matching submission entities.

        Args:
            project_id: the project id.
            name: filter by submission name.
            is_published: filter by published status.
            is_ingested: filter by ingested status.
            created_start: filter by submission creation date range.
            created_end: filter by submission creation date range.
            modified_start: filter by submission modified date range.
            modified_end: filter by submission modified date range.
            sort: how the submissions are sorted.
            page: The page number.
            page_size: The page size.

        Returns:
            A tuple containing:
                - List of matching and optionally paginated submission entities.
                - Total number of matching submission entities.
        """
        is_paginated = page is not None and page_size is not None
        offset = (page - 1) * page_size if is_paginated else None

        # Apply filters.
        filters = [SubmissionEntity.project_id == project_id]

        if name is not None:
            escaped_name = name.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            filters.append(SubmissionEntity.name.like(f"%{escaped_name}%", escape="\\"))

        if is_published is not None:
            filters.append(SubmissionEntity.is_published == is_published)
        if is_ingested is not None:
            filters.append(SubmissionEntity.is_ingested == is_ingested)

        if created_start is not None and created_end is not None:
            filters.append(func.date(SubmissionEntity.created).between(created_start.date(), created_end.date()))
        elif created_start is not None:
            filters.append(func.date(SubmissionEntity.created) >= created_start.date())
        elif created_end is not None:
            filters.append(func.date(SubmissionEntity.created) <= created_end.date())

        if modified_start is not None and modified_end is not None:
            filters.append(func.date(SubmissionEntity.modified).between(modified_start.date(), modified_end.date()))
        elif modified_start is not None:
            filters.append(func.date(SubmissionEntity.modified) >= modified_start.date())
        elif modified_end is not None:
            filters.append(func.date(SubmissionEntity.modified) <= modified_end.date())
        # Select submissions.

        stmt = select(SubmissionEntity).where(and_(*filters)).order_by(sort.value)
        if is_paginated:
            stmt = stmt.offset(offset).limit(page_size)

        async with transaction(self._session_factory) as session:
            result = await session.execute(stmt)
            submissions = result.scalars().all()

            if is_paginated:
                total_stmt = (
                    select(func.count())  # pylint: disable=not-callable
                    .select_from(SubmissionEntity)
                    .where(and_(*filters))
                )
                total_result = await session.execute(total_stmt)
                total = total_result.scalar_one()
            else:
                total = len(submissions)

        return submissions, total

    async def update_submission(
        self, submission_id: str, update_callback: Callable[[SubmissionEntity], Awaitable[None]]
    ) -> SubmissionEntity | None:
        """
        Update the submission entity.

        Args:
            submission_id: the submission id.
            update_callback: A coroutine function that updates the submission entity.

        Returns:
            The updated submission entity or None if the submission id was not found.
        """
        async with transaction(self._session_factory):
            submission = await self.get_submission_by_id(submission_id)

            if submission is None:
                return None
            await update_callback(submission)

            # Validate submission document.
            Submission.model_validate(submission.document)

            return submission

    async def delete_submission_by_id(self, submission_id: str) -> bool:
        """
        Delete the submission entity using submission id.

        Args:
            submission_id: The submission id.

        Returns:
            True if the submission was deleted, False otherwise.
        """
        async with transaction(self._session_factory) as session:
            stmt = delete(SubmissionEntity).where(SubmissionEntity.submission_id == submission_id)
            result = await session.execute(stmt)
            return result.rowcount > 0  # type: ignore

    async def delete_submission_by_name(self, project_id: str, name: str) -> bool:
        """
        Delete the submission entity using submission name.

        Args:
            project_id: The project id.
            name: The submission name.

        Returns:
            True if the submission was deleted, False otherwise.
        """
        async with transaction(self._session_factory) as session:
            stmt = delete(SubmissionEntity).where(
                SubmissionEntity.project_id == project_id, SubmissionEntity.name == name
            )
            result = await session.execute(stmt)
            return result.rowcount > 0  # type: ignore

    async def delete_submission_by_id_or_name(self, project_id: str, submission_id: str) -> bool:
        """
        Delete the submission entity using submission id or name.

        Args:
            project_id: The project id.
            submission_id: The submission id or name.

        Returns:
            True if the submission was deleted, False otherwise.
        """

        deleted = await self.delete_submission_by_id(submission_id)
        if not deleted:
            deleted = await self.delete_submission_by_name(project_id, submission_id)

        return deleted
