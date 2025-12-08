"""Service for submissions."""

from datetime import datetime
from typing import Any

from ....api.exceptions import NotFoundUserException, UserException
from ....api.json import to_json_dict
from ....api.models.submission import Rems, Submission, SubmissionMetadata, Submissions, SubmissionWorkflow
from ..models import SubmissionEntity
from ..repositories.registration import RegistrationRepository
from ..repositories.submission import (
    SUB_FIELD_BUCKET,
    SUB_FIELD_METADATA,
    SUB_FIELD_REMS,
    SubmissionRepository,
    SubmissionSort,
)


class UnknownSubmissionUserException(NotFoundUserException):
    """Raised when a submission cannot be found."""

    def __init__(self, submission_id: str) -> None:
        """
        Initialize the exception.

        :param submission_id: the submission id
        """
        message = f"Submission '{submission_id}' not found."
        super().__init__(message)


class PublishedSubmissionUserException(UserException):
    """Raised when a submission has been published and can't be modified."""

    def __init__(self, submission_id: str) -> None:
        """
        Initialize the exception.

        :param submission_id: the submission id
        """
        message = f"Submission '{submission_id}' has been published and can no longer be modified."
        super().__init__(message)


class SubmissionService:
    """Service for submissions."""

    def __init__(self, repository: SubmissionRepository, registration_repository: RegistrationRepository) -> None:
        """Initialize the service."""
        self.repository = repository
        self.registration_repository = registration_repository

    @staticmethod
    def ignore_fields(submission: Submission) -> None:
        """
        Ignore fields in the submission document.

        :param submission: the submission document
        """
        submission.submissionId = None
        submission.published = None
        submission.dateCreated = None
        submission.lastModified = None
        submission.datePublished = None
        if submission.metadata:
            submission.metadata.identifiers = None

    @staticmethod
    def convert_to_new_entity(submission: Submission) -> SubmissionEntity:
        """
        Convert submission document to a new submission entity.

        :param submission: The new submission document
        "return: The submission entity
        """
        # Create a copy so that the original document is not modified.
        submission = submission.model_copy(deep=True)

        SubmissionService.ignore_fields(submission)

        try:
            workflow = SubmissionWorkflow(submission.workflow)
        except ValueError:
            raise UserException(f"Invalid submission workflow: {submission.workflow.value}")

        entity = SubmissionEntity(name=submission.name, project_id=submission.projectId, workflow=workflow)
        SubmissionService._set_updatable_values(submission, entity)
        return entity

    @staticmethod
    def _set_updatable_values(submission: Submission, entity: SubmissionEntity) -> None:
        entity.bucket = submission.bucket
        entity.title = submission.title
        entity.description = submission.description
        entity.document = to_json_dict(submission)

    @staticmethod
    async def convert_to_updated_entity(submission: dict[str, Any], old_entity: SubmissionEntity) -> SubmissionEntity:
        """
        Convert submission document to an updated submission entity.

        :param submission: A completely or partially updated submission document.
        :param old_entity: The old submission entity.
        "return: The submission entity
        """
        old_submission = await SubmissionService.convert_from_entity(old_entity)

        SubmissionService.ignore_fields(old_submission)

        # Merge changes to the existing submission document.
        updated_submission = Submission.model_validate({**to_json_dict(old_submission), **submission})

        # Some field values can't be changed.
        if updated_submission.name != old_entity.name:
            raise UserException(f"Submission name '{old_entity.name}' can't be changed to '{updated_submission.name}'")
        if updated_submission.workflow != old_entity.workflow:
            raise UserException(
                f"Submission workflow '{old_entity.workflow.value}' can't be changed to '{updated_submission.workflow}'"
            )
        if updated_submission.projectId != old_entity.project_id:
            raise UserException(
                f"Submission project '{old_entity.project_id}' can't be changed to '{updated_submission.projectId}'"
            )
        if old_entity.bucket and updated_submission.bucket != old_entity.bucket:
            raise UserException(
                f"Submission bucket '{old_entity.bucket}' can't be changed to '{updated_submission.bucket}'"
            )

        SubmissionService._set_updatable_values(updated_submission, old_entity)
        return old_entity

    @staticmethod
    async def convert_from_entity(entity: SubmissionEntity) -> Submission | None:
        """
        Convert submission JSON document to a submission model.

        :param entity: the submission entity
        :returns: the submission document
        """

        if entity is None:
            return None

        # Make a deepcopy to prevent SQLAlchemy from tracking changes.
        submission = Submission.model_validate(entity.document).model_copy(deep=True)

        submission.submissionId = entity.submission_id
        submission.published = entity.is_published
        if entity.bucket is not None:
            submission.bucket = entity.bucket
        if entity.created is not None:
            submission.dateCreated = entity.created
        if entity.modified is not None:
            submission.lastModified = entity.modified
        if entity.published is not None:
            submission.datePublished = entity.published

        return submission

    async def add_submission(self, submission: Submission, *, submission_id: str | None = None) -> str:
        """Add a new submission to the database.

        :param submission: the submission
        :param submission_id: submission id that overrides the default one
        :returns: the automatically assigned submission id
        """

        # Check that the submission name does not already exist in the project.
        if await self.is_submission_by_name(submission.projectId, submission.name):
            raise UserException(
                f"Submission with name {submission.name} already exists in project {submission.projectId}"
            )

        entity = self.convert_to_new_entity(submission)
        entity.submission_id = submission_id

        return await self.repository.add_submission(entity)

    async def get_submission_by_id(self, submission_id: str) -> Submission | None:
        """Get the submission using submission id.

        :param submission_id: the submission id
        :returns: the submission
        """
        return await self.convert_from_entity(await self.repository.get_submission_by_id(submission_id))

    async def get_submission_by_name(self, project_id: str, name: str) -> Submission | None:
        """Get the submission using submission name.

        :param project_id: The project_id.
        :param name: The name of the submission.
        """
        return await self.convert_from_entity(await self.repository.get_submission_by_name(project_id, name))

    async def get_submission_by_id_or_name(self, project_id: str, submission_id_or_name: str) -> Submission | None:
        """Get the submission using submission id or name.

        :param project_id: the project id
        :param submission_id_or_name: the submission id or submission name
        :returns: submission id if the submission exists
        """
        submission = await self.get_submission_by_id(submission_id_or_name)
        if not submission:
            submission = await self.get_submission_by_name(project_id, submission_id_or_name)

        return submission

    async def get_submissions(
        self,
        project_id: str,
        *,
        name: str | None = None,
        is_published: bool | None = None,
        is_ingested: bool | None = None,
        created_start: datetime | None = None,
        created_end: datetime | None = None,
        modified_start: datetime | None = None,
        modified_end: datetime | None = None,
        sort: SubmissionSort = SubmissionSort.CREATED_DESC,
        page: int | None = None,
        page_size: int | None = None,
    ) -> tuple[Submissions, int]:
        """
        Get matching submissions.

        Args:
            project_id: the project id.
            name: the submission name.
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
                - List of matching and optionally paginated submissions.
                - Total number of matching submissions.
        """
        submissions, cnt = await self.repository.get_submissions(
            project_id,
            name=name,
            is_published=is_published,
            is_ingested=is_ingested,
            created_start=created_start,
            created_end=created_end,
            modified_start=modified_start,
            modified_end=modified_end,
            sort=sort,
            page=page,
            page_size=page_size,
        )

        return Submissions(submissions=[await self.convert_from_entity(s) for s in submissions]), cnt

    async def is_submission_by_id(self, submission_id: str) -> bool:
        """Check if the submission exists.

        :param submission_id: the submission id
        :returns: True if the submission exists
        """
        submission = await self.repository.get_submission_by_id(submission_id)
        return submission is not None

    async def check_submission_by_id(self, submission_id: str) -> None:
        """Raise an exception if the submission does not exist.

        :param submission_id: the submission id
        """
        if not await self.is_submission_by_id(submission_id):
            raise UnknownSubmissionUserException(submission_id)

    async def is_submission_by_name(self, project_id: str, name: str) -> bool:
        """Check if the submission exists.

        :param project_id: the project id
        :param name: the submission name
        :returns: True if the submission exists
        """
        submission = await self.repository.get_submission_by_name(project_id, name)
        return submission is not None

    async def check_submission_by_name(self, project_id: str, name: str) -> str:
        """Raise an exception if the submission does not exist.

        :param project_id: the project id
        :param name: the submission name
        :returns: The submission id
        """
        submission = await self.repository.get_submission_by_name(project_id, name)
        if not submission:
            raise UnknownSubmissionUserException(name)
        return submission.submission_id

    async def check_submission_by_id_or_name(self, project_id: str, submission_id_or_name: str) -> str:
        """Raise an exception if the submission does not exist.

        :param project_id: the project id
        :param submission_id_or_name: the submission id or submission name
        :returns: submission id if the submission exists
        """
        if await self.is_submission_by_id(submission_id_or_name):
            return submission_id_or_name

        submission = await self.repository.get_submission_by_name(project_id, submission_id_or_name)
        if submission:
            return submission.submission_id

        raise UnknownSubmissionUserException(submission_id_or_name)

    async def is_published(self, submission_id: str) -> bool:
        """Check if the submission has been published.

        :param submission_id: the submission id
        :returns: True if the submission has been published
        """
        submission = await self.repository.get_submission_by_id(submission_id)
        if submission is None:
            raise UnknownSubmissionUserException(submission_id)

        return submission.is_published is True

    async def check_not_published(self, submission_id: str) -> None:
        """Raise an exception if the submission has been published.

        :param submission_id: the submission id
        """
        if await self.is_published(submission_id):
            raise PublishedSubmissionUserException(submission_id)

    async def get_project_id(self, submission_id: str) -> str:
        """Get the project id for the submission.

        :param submission_id: the submission id
        :returns: The project id.
        """
        submission = await self.repository.get_submission_by_id(submission_id)
        if submission is None:
            raise UnknownSubmissionUserException(submission_id)

        return submission.project_id

    async def get_workflow(self, submission_id: str) -> SubmissionWorkflow:
        """Get the workflow for the submission.

        :param submission_id: the submission id
        :returns: The submission workflow.
        """
        submission = await self.repository.get_submission_by_id(submission_id)
        if submission is None:
            raise UnknownSubmissionUserException(submission_id)

        return submission.workflow

    async def get_metadata(self, submission_id: str) -> SubmissionMetadata | None:
        """Get submission metadata sub-document.

        :param submission_id: the submission id
        :returns: The submission metadata sub-document.
        """

        submission = await self.repository.get_submission_by_id(submission_id)
        if submission is None:
            raise UnknownSubmissionUserException(submission_id)

        return SubmissionMetadata.model_validate(submission.document[SUB_FIELD_METADATA])

    async def get_rems_document(self, submission_id: str) -> Rems | None:
        """Get REMS sub-document.

        :param submission_id: the submission id
        :returns: The REMS sub-document
        """

        submission = await self.repository.get_submission_by_id(submission_id)
        if submission is None:
            raise UnknownSubmissionUserException(submission_id)

        if SUB_FIELD_REMS in submission.document:
            return Rems.model_validate(submission.document[SUB_FIELD_REMS])
        return None

    async def get_bucket(self, submission_id: str) -> str | None:
        """Get the name of the bucket linked to the submission.

        :param submission_id: the submission id
        :returns: The bucket name
        """
        submission = await self.repository.get_submission_by_id(submission_id)
        if submission is None:
            raise UnknownSubmissionUserException(submission_id)

        return submission.bucket

    async def update_submission(self, submission_id: str, document: dict[str, Any]) -> None:
        """Update the existing submission document.

        :param submission_id: the submission id
        :param document: a completely or partially updated submission document
        """

        async def update_callback(submission: SubmissionEntity) -> None:
            await self.convert_to_updated_entity(document, submission)

        if await self.repository.update_submission(submission_id, update_callback) is None:
            raise UnknownSubmissionUserException(submission_id)

    async def update_bucket(self, submission_id: str, bucket: str) -> None:
        """Update submission bucket.

        :param submission_id: the submission id
        :param bucket: new bucket
        """
        await self.update_submission(submission_id, {SUB_FIELD_BUCKET: bucket})

    async def update_metadata(self, submission_id: str, metadata: SubmissionMetadata) -> None:
        """Update submission metadata sub-document.

        :param submission_id: the submission id
        :param metadata: new submission metadata
        """
        await self.update_submission(submission_id, {SUB_FIELD_METADATA: to_json_dict(metadata)})

    async def update_rems(self, submission_id: str, rems: Rems) -> None:
        """Update dataset REMS resource information.

        :param submission_id: the submission id
        :param rems: REMS data.
        """
        await self.update_submission(submission_id, {SUB_FIELD_REMS: to_json_dict(rems)})

    async def publish(self, submission_id: str) -> None:
        """Publish the submission.

        :param submission_id: the submission id
        """

        async def update_callback(submission: SubmissionEntity) -> None:
            if not submission.is_published:
                submission.is_published = True

        if await self.repository.update_submission(submission_id, update_callback) is None:
            raise UnknownSubmissionUserException(submission_id)

    async def delete_submission(self, submission_id: str) -> None:
        """Delete submission.

        :param submission_id: the submission id
        """
        await self.repository.delete_submission_by_id(submission_id)
