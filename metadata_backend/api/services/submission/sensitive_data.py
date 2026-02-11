"""Service for processing Sensitive Data submissions."""

import json
from typing import override

from ....database.postgres.services.file import FileService
from ....database.postgres.services.object import ObjectService
from ....database.postgres.services.submission import SubmissionService
from ...exceptions import UserException
from ...json import to_json_dict
from ...models.models import File
from ...models.submission import Submission, SubmissionWorkflow
from ...processors.xml.processors import XmlStringDocumentsProcessor
from ..accession import generate_submission_accession
from ..project import ProjectService
from .submission import ObjectSubmission, ObjectSubmissionService

# mypy: disable_error_code = misc

SD_FILE = "submission.json"


class SensitiveDataObjectSubmissionService(ObjectSubmissionService):
    """Service for processing SD submissions."""

    def __init__(
        self,
        project_service: ProjectService,
        submission_service: SubmissionService,
        object_service: ObjectService,
        file_service: FileService,
    ) -> None:
        """
        Service for processing SD submissions.

        :param project_service: The Postgres project service.
        :param submission_service: The Postgres submission service.
        :param object_service: The Postgres object service.
        :param file_service: The Postgres file service.
        """

        self._submission_document: str | None = None

        super().__init__(
            project_service=project_service,
            submission_service=submission_service,
            object_service=object_service,
            file_service=file_service,
            workflow=SubmissionWorkflow.SD,
            supports_updates=True,
            supports_references=False,
        )

    @override
    def create_processor(self, objects: list[ObjectSubmission]) -> XmlStringDocumentsProcessor | None:
        """
        Create XML documents processor.

        :param objects: The metadata object documents.
        :return: the XML documents processor.
        """

        self._submission_document = self._get_object(objects).document

        return None

    @override
    def assign_submission_accession(self) -> str | None:
        """
        Assign submission accession number.

        :return: the submission id.
        """

        return generate_submission_accession(self._workflow)

    @override
    def prepare_create_submission(self, project_id: str, submission_id: str) -> Submission:
        """
        Prepare submission document.

        :param project_id: The project id.
        :param submission_id: The submission id.
        :return: The submission document.
        """

        return Submission.model_validate_json(
            self._submission_document, context={"projectId": project_id, "workflow": SubmissionWorkflow.SD.value}
        )

    @override
    def prepare_update_submission(self, old_submission: Submission) -> Submission:
        """
        Prepare submission document.

        :param old_submission: The existing submission.
        :return: The submission document.
        """
        # Merge changes to the existing submission document.
        return Submission.model_validate({**to_json_dict(old_submission), **json.loads(self._submission_document)})

    @override
    def prepare_files(self, submission_id: str) -> list[File]:
        """
        Prepare submission files.

        :param submission_id: The submission id.
        :return: The submission files.
        """

        # Files are added during publish.

        return []

    @staticmethod
    def _get_object(objects: list[ObjectSubmission]) -> ObjectSubmission:
        """
        Get submission object.

        :param objects: The metadata object documents.
        :return: the submission object.
        """
        if len(objects) != 1:
            raise UserException(f"Expected only one file: {SD_FILE}")

        obj = objects[0]
        filename_lower = obj.filename.lower()
        if filename_lower != SD_FILE:
            raise UserException(f"Invalid file name: {obj.filename}. Expected file name: '{SD_FILE}'. ")

        return obj
