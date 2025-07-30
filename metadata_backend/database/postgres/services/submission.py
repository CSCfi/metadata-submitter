"""Service for submissions."""

import copy
import re
from datetime import datetime
from typing import Any, cast

from ....api.exceptions import NotFoundUserException, UserException
from ....api.models import Rems, SubmissionWorkflow
from ..models import SubmissionEntity
from ..repositories.submission import (
    SUB_FIELD_CREATED_DATE,
    SUB_FIELD_DESCRIPTION,
    SUB_FIELD_DOI,
    SUB_FIELD_FOLDER,
    SUB_FIELD_MODIFIED_DATE,
    SUB_FIELD_NAME,
    SUB_FIELD_PROJECT_ID,
    SUB_FIELD_PUBLISHED,
    SUB_FIELD_PUBLISHED_DATE,
    SUB_FIELD_REMS,
    SUB_FIELD_SUBMISSION_ID,
    SUB_FIELD_WORKFLOW,
    SubmissionRepository,
    SubmissionSort,
)

# pylint: disable=too-many-public-methods


class SubmissionUserException(UserException):
    """Base exception for submission related user errors."""


class UnknownSubmissionUserException(NotFoundUserException):
    """Raised when a submission cannot be found."""

    def __init__(self, submission_id: str) -> None:
        """
        Initialize the exception.

        :param submission_id: the submission id
        """
        message = f"Submission '{submission_id}' not found."
        super().__init__(message)


class PublishedSubmissionUserException(SubmissionUserException):
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

    def __init__(self, repository: SubmissionRepository) -> None:
        """Initialize the service."""
        self.repository = repository

    @staticmethod
    def _copy_str_field(document: dict[str, Any], name: str, *, mandatory: bool = False) -> str | None:
        """
        Read a string field from the submission document.

        :param document: The submission document.
        :param name: The field name.
        :param mandatory: Whether the field is mandatory.
        :return: The value as a string if the field exists and can be
        converted to a string. Mandatory fields raise ValueError if the field
        is missing or can't be converted to a string.
        """
        value = document
        try:
            value = value[name]
            return str(value)
        except (KeyError, TypeError, ValueError):
            if mandatory:
                raise ValueError(f"Missing or invalid submission field: {name}")  # pylint: disable=raise-missing-from
            return None

    @staticmethod
    def _remove_field(document: dict[str, Any], *names: str) -> None:
        """
        Remove fields from submissions document.

        :param document: The submission document.
        :param names: The field names.
        """
        for name in names:
            document.pop(name, None)

    @staticmethod
    def _preserve_immutable_field(document: dict[str, Any], old_document: dict[str, Any], name: str) -> None:
        """
        Preserve immutable field value by copying it from the old submission document.

        :param document: The submission document.
        :param old_document: The old submission document.
        :param name: The field name.
        """
        old_value = SubmissionService._copy_str_field(old_document, name)
        if old_value:
            # Keep old value regardless of the new value.
            document[name] = old_value

    @staticmethod
    def _preserve_mutable_field(document: dict[str, Any], old_document: dict[str, Any], name: str) -> None:
        """
        Preserve mutable field value by copying it from the old submission document if it has been removed.

        :param document: The submission document.
        :param old_document: The old submission document.
        :param name: The field name.
        """
        value = document.get(name)
        old_value = old_document.get(name)
        if old_value and not value:
            # Keep old value if new value has not been defined.
            document[name] = old_value

    @staticmethod
    def convert_to_entity(document: dict[str, Any], old_submission: SubmissionEntity | None = None) -> SubmissionEntity:
        """
        Convert submission document to a submission entity.

        :param document: The new submission document
        :param old_submission: The old submission entity if one exists.
        "return: The submission entity
        """
        new_document = copy.deepcopy(document)  # Create a copy so that the document is not modified.

        _copy_str_field = SubmissionService._copy_str_field
        _preserve_immutable_field = SubmissionService._preserve_immutable_field
        _preserve_mutable_field = SubmissionService._preserve_mutable_field
        _remove_field = SubmissionService._remove_field

        # Ignored in the submission document.
        _remove_field(
            new_document,
            SUB_FIELD_SUBMISSION_ID,
            SUB_FIELD_PUBLISHED,
            SUB_FIELD_CREATED_DATE,
            SUB_FIELD_MODIFIED_DATE,
            SUB_FIELD_PUBLISHED_DATE,
            # No longer supported.
            "metadataObjects",
            "drafts",
            "files",
            "extraInfo",
        )

        if not old_submission:
            # Create new submission.
            name = _copy_str_field(new_document, SUB_FIELD_NAME, mandatory=True)
            project_id = _copy_str_field(new_document, SUB_FIELD_PROJECT_ID, mandatory=True)
            folder = _copy_str_field(new_document, SUB_FIELD_FOLDER)
            workflow_str = _copy_str_field(new_document, SUB_FIELD_WORKFLOW, mandatory=True)
            try:
                workflow = SubmissionWorkflow(workflow_str)
            except ValueError:
                raise UserException(  # pylint: disable=raise-missing-from
                    f"Invalid submission workflow: {workflow_str}"
                )

            return SubmissionEntity(
                name=name,
                project_id=project_id,
                folder=folder,
                workflow=workflow,
                document=new_document,
            )

        # Update existing submission.

        # The submission document can be updated by the user, however, some fields
        # can't be removed or changed. If the following fields are absent from the
        # updated document then the existing value in the current document is preserved:
        # name, description, doiInfo, rems, projectId, workflow, linkedFolder. Furthermore,
        # if the following fields are changed then the existing value in the current document
        # is preserved: projectId, workflow, linkedFolder.

        old_document = old_submission.document
        _preserve_mutable_field(new_document, old_document, SUB_FIELD_NAME)
        _preserve_mutable_field(new_document, old_document, SUB_FIELD_DESCRIPTION)
        _preserve_immutable_field(new_document, old_document, SUB_FIELD_PROJECT_ID)
        _preserve_immutable_field(new_document, old_document, SUB_FIELD_FOLDER)
        _preserve_immutable_field(new_document, old_document, SUB_FIELD_WORKFLOW)
        _preserve_mutable_field(new_document, old_document, SUB_FIELD_DOI)
        _preserve_mutable_field(new_document, old_document, SUB_FIELD_REMS)

        old_submission.name = _copy_str_field(new_document, SUB_FIELD_NAME)
        old_submission.folder = _copy_str_field(new_document, SUB_FIELD_FOLDER)
        old_submission.document = new_document
        return old_submission

    @staticmethod
    def convert_from_entity(entity: SubmissionEntity) -> dict[str, Any] | None:
        """
        Convert submission JSON document to a submission dict.

        :param entity: the submission entity
        :returns: the submission dict
        """

        if entity is None:
            return None

        # Make a deepcopy to prevent SQLAlchemy from tracking changes to the document.
        document = copy.deepcopy(entity.document)

        document[SUB_FIELD_SUBMISSION_ID] = entity.submission_id
        document[SUB_FIELD_PROJECT_ID] = entity.project_id
        document[SUB_FIELD_NAME] = entity.name
        document["text_name"] = " ".join(re.split("[\\W_]", entity.name))
        document[SUB_FIELD_WORKFLOW] = entity.workflow.value
        document[SUB_FIELD_PUBLISHED] = entity.is_published
        if entity.folder is not None:
            document[SUB_FIELD_FOLDER] = entity.folder
        if entity.created is not None:
            document[SUB_FIELD_CREATED_DATE] = entity.created
        if entity.modified is not None:
            document[SUB_FIELD_MODIFIED_DATE] = entity.modified
        if entity.published is not None:
            document[SUB_FIELD_PUBLISHED_DATE] = entity.published

        return document

    async def add_submission(self, submission: dict[str, Any]) -> str:
        """Add a new submission to the database.

        :param submission: the submission
        :returns: the automatically assigned submission id
        """
        return await self.repository.add_submission(self.convert_to_entity(submission))

    async def get_submission_by_id(self, submission_id: str) -> dict[str, Any] | None:
        """Get the submission using submission id.

        :param submission_id: the submission id
        :returns: the submission
        """
        return self.convert_from_entity(await self.repository.get_submission_by_id(submission_id))

    async def get_submission_by_name(self, project_id: str, name: str) -> dict[str, Any] | None:
        """Get the submission using submission name.

        :param project_id: The project_id.
        :param name: The name of the submission.
        """
        return self.convert_from_entity(await self.repository.get_submission_by_name(project_id, name))

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
    ) -> tuple[list[dict[str, Any]], int]:
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

        return [self.convert_from_entity(submission) for submission in submissions], cnt

    async def is_submission(self, submission_id: str) -> bool:
        """Check if the submission exists.

        :param submission_id: the submission id
        :returns: True if the submission exists
        """
        submission = await self.repository.get_submission_by_id(submission_id)
        return submission is not None

    async def check_submission(self, submission_id: str) -> None:
        """Raise an exception if the submission does not exist.

        :param submission_id: the submission id
        """
        if not await self.is_submission(submission_id):
            raise UnknownSubmissionUserException(submission_id)

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

    async def get_doi_document(self, submission_id: str) -> dict[str, Any] | None:
        """Get DOI sub-document.

        :param submission_id: the submission id
        :returns: The DOI sub-document.
        """

        submission = await self.repository.get_submission_by_id(submission_id)
        if submission is None:
            raise UnknownSubmissionUserException(submission_id)

        if SUB_FIELD_DOI in submission.document:
            return cast(dict[str, Any], submission.document[SUB_FIELD_DOI])
        return None

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

    async def update_submission(self, submission_id: str, document: dict[str, Any]) -> None:
        """Update the submission document.

        The submission document can be updated by the user, however, some fields
        can't be removed or changed. If the following fields are absent from the
        updated document then the existing value in the current document is preserved:
        name, description, doiInfo, rems, projectId, workflow, linkedFolder. Furthermore,
        if the following fields are changed then the existing value in the current document
        is preserved: projectId, workflow, linkedFolder.

        :param submission_id: the submission id
        :param document: the new submission document
        """

        def update_callback(submission: SubmissionEntity) -> None:
            self.convert_to_entity(document, submission)

        if await self.repository.update_submission(submission_id, update_callback) is None:
            raise UnknownSubmissionUserException(submission_id)

    async def update_name(self, submission_id: str, name: str) -> None:
        """Update submission name.

        :param submission_id: the submission id
        :param name: new name
        """

        def update_callback(submission: SubmissionEntity) -> None:
            submission.name = name

        if await self.repository.update_submission(submission_id, update_callback) is None:
            raise UnknownSubmissionUserException(submission_id)

    async def update_description(self, submission_id: str, description: str) -> None:
        """Update submission description.

        :param submission_id: the submission id
        :param description: new description
        """

        def update_callback(submission: SubmissionEntity) -> None:
            submission.document["description"] = description

        if await self.repository.update_submission(submission_id, update_callback) is None:
            raise UnknownSubmissionUserException(submission_id)

    async def update_folder(self, submission_id: str, folder: str) -> None:
        """Update submission folder.

        :param submission_id: the submission id
        :param folder: new folder
        """

        def update_callback(submission: SubmissionEntity) -> None:
            if submission.folder is not None:
                raise SubmissionUserException(f"Submission '{submission_id}' already has a linked folder.")
            submission.folder = folder

        if await self.repository.update_submission(submission_id, update_callback) is None:
            raise UnknownSubmissionUserException(submission_id)

    async def update_doi_info(self, submission_id: str, doi_info: dict[str, Any]) -> None:
        """Update submission doi info.

        :param submission_id: the submission id
        :param doi_info: new doi info
        """

        def update_callback(submission: SubmissionEntity) -> None:
            submission.document[SUB_FIELD_DOI] = doi_info

        if await self.repository.update_submission(submission_id, update_callback) is None:
            raise UnknownSubmissionUserException(submission_id)

    async def update_rems(self, submission_id: str, rems: Rems) -> None:
        """Update dataset REMS resource information.

        :param submission_id: the submission id
        :param rems: REMS data.
        """

        def update_callback(submission: SubmissionEntity) -> None:
            submission.document[SUB_FIELD_REMS] = rems.json_dump()

        if await self.repository.update_submission(submission_id, update_callback) is None:
            raise UnknownSubmissionUserException(submission_id)

    async def publish(self, submission_id: str) -> None:
        """Publish the submission.

        :param submission_id: the submission id
        """

        def update_callback(submission: SubmissionEntity) -> None:
            if not submission.is_published:
                submission.is_published = True

        if await self.repository.update_submission(submission_id, update_callback) is None:
            raise UnknownSubmissionUserException(submission_id)

    async def delete_submission(self, submission_id: str) -> None:
        """Delete submission.

        :param submission_id: the submission id
        """
        await self.repository.delete_submission_by_id(submission_id)
