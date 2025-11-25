"""Service for processing metadata object submissions."""

# mypy: disable_error_code = misc

from abc import ABC, abstractmethod
from collections import defaultdict
from typing import Sequence

from pydantic import BaseModel, ValidationError

from ....database.postgres.repository import SessionFactory, transaction
from ....database.postgres.services.file import FileService
from ....database.postgres.services.object import ObjectService
from ....database.postgres.services.submission import SubmissionService
from ...exceptions import SystemException, UserErrors, UserException
from ...json import to_json_dict
from ...models.models import File
from ...models.submission import Submission, SubmissionWorkflow
from ...processors.models import ObjectIdentifier
from ...processors.processors import DocumentsProcessor, ObjectProcessor
from ...processors.xml.processors import XmlObjectProcessor
from ..accession import generate_accession
from ..project import ProjectService


class ObjectSubmission(BaseModel):
    """Metadata object submission file."""

    filename: str
    document: str

    model_config = {"frozen": True}


# TODO(improve): test update with new and deleted metadata objects


class ObjectSubmissionService(ABC):
    """Service for processing metadata object submissions."""

    @abstractmethod
    def create_processor(self, objects: list[ObjectSubmission]) -> DocumentsProcessor | None:
        """
        Create documents processor.

        :param objects: The metadata object documents.
        :return: The documents processor.
        """

    @abstractmethod
    def assign_submission_accession(self) -> str | None:
        """
        Assign submission accession number.

        :return: the submission id.
        """

    @abstractmethod
    def prepare_create_submission(self, project_id: str, submission_id: str) -> Submission:
        """
        Prepare submission document.

        :param project_id: The project id.
        :param submission_id: The submission id.
        :return: The submission document.
        """

    def prepare_update_submission(self, old_submission: Submission) -> Submission:
        """
        Prepare submission document.

        :param old_submission: The existing submission.
        :return: The submission document.
        """
        return self.prepare_create_submission(old_submission.projectId, old_submission.submissionId)

    @abstractmethod
    def prepare_files(self, submission_id: str) -> list[File]:
        """
        Prepare submission files.

        :param submission_id: The submission id.
        """

    def __init__(
        self,
        project_service: ProjectService,
        submission_service: SubmissionService,
        object_service: ObjectService,
        file_service: FileService,
        session_factory: SessionFactory,
        workflow: SubmissionWorkflow,
        supports_updates: bool,
        supports_references: bool,
    ) -> None:
        """
        Service for processing submission with metadata objects.

        :param project_service: The Postgres project service.
        :param submission_service: The Postgres submission service.
        :param object_service: The Postgres object service.
        :param file_service: The Postgres file service.
        :param session_factory: The SQLAlchemy session factory.
        :param workflow: The submission workflow.
        :param supports_updates: Are metadata object updates supported.
        :param supports_references: Are references to previously submitted metadata objects are supported.
        """

        self._project_service = project_service
        self._submission_service = submission_service
        self._object_service = object_service
        self._file_service = file_service
        self._session_factory = session_factory
        self._workflow = workflow
        self._supports_updates = supports_updates
        self._supports_references = supports_references

    async def create(self, user_id: str, project_id: str, objects: list[ObjectSubmission]) -> Submission:
        """
        Create a new submission.

        :param user_id: The user id.
        :param project_id: The project id.
        :param objects: The metadata object documents.
        :returns: The submission document.
        :raises UserErrors: If case of any user errors.
        """

        errors: list[str] = []

        try:
            # Check that user is affiliated with the project.
            await self._project_service.verify_user_project(user_id, project_id)

            processor = self.create_processor(objects)
            object_identifiers: Sequence[ObjectIdentifier] = []
            if processor:
                # Get metadata object identifiers.
                object_identifiers = processor.get_object_identifiers()

                # Check that no metadata objects are accessioned.
                for identifier in object_identifiers:
                    if identifier.id is not None:
                        errors.append(
                            f"Update of previously submitted '{identifier.schema_type}' metadata object '{identifier.id}'"
                            "is not supported"
                        )

                if not self._supports_references:
                    # Check that no metadata object references are accessioned.
                    for identifier in processor.get_object_references():
                        if identifier.id is not None:
                            errors.append(
                                f"Reference to previously submitted '{identifier.schema_type}' metadata object "
                                f"'{identifier.id}' is not supported"
                            )

                if errors:
                    raise UserErrors(errors)

            if processor:
                # Assign metadata object accessions.
                for identifier in object_identifiers:
                    identifier.id = generate_accession(self._workflow, identifier.object_type)
                    processor.set_object_id(identifier)

                # Check that all metadata object references have accessions.
                for identifier in processor.get_references_without_ids():
                    errors.append(f"Unknown '{identifier.schema_type}' metadata object '{identifier.id}' reference")

            # Assign submission accession.
            submission_id = self.assign_submission_accession()

            if submission_id is None:
                raise SystemException("Failed to assign submission id")

            # Prepare submission document.
            submission = self.prepare_create_submission(project_id, submission_id)

            # Prepare submission files.
            files = self.prepare_files(submission_id)

            # Create and save submission and metadata objects within one transaction.
            async with transaction(self._session_factory):

                # Add submission.
                saved_submission_id = await self._submission_service.add_submission(
                    submission, submission_id=submission_id
                )
                if saved_submission_id != submission_id:
                    raise SystemException("Failed to save generated submission id")

                # Get saved submission.
                submission = Submission.model_validate(
                    await self._submission_service.get_submission_by_id(submission_id)
                )

                if processor:
                    # Add metadata objects.
                    for identifier in object_identifiers:
                        object_processor = await self._get_object_processor(identifier, processor)

                        await self._add_object(project_id, submission_id, identifier, object_processor)

                # Save files.
                for file in files:
                    await self._file_service.add_file(file, self._workflow)

        except ValidationError as e:
            # Preserve Pydantic validation error.
            raise e
        except Exception as e:
            errors.append(str(e))
            raise UserErrors(errors) from e

        return submission

    async def update(
        self, user_id: str, project_id: str, submission_id: str, objects: list[ObjectSubmission]
    ) -> Submission:
        """
        Update an existing submission.

        :param user_id: The user id.
        :param project_id: The project id.
        :param submission_id: The submission id.
        :param objects: The metadata object documents.
        :returns: The submission document.
        :raises UserErrors: If case of any user errors.
        """

        if not self._supports_updates:
            raise UserException(f"Submission updates are not supported for workflow '{self._workflow}'")

        errors: list[str] = []

        try:
            # Check that user is affiliated with the project.
            await self._project_service.verify_user_project(user_id, project_id)

            new_object_identifiers = []
            updated_object_identifiers = []
            deleted_objects = []

            processor = self.create_processor(objects)

            if processor:
                # Get metadata object identifiers.
                identifiers = processor.get_object_identifiers()

                # Get existing metadata objects.
                old_objects = await self._object_service.get_objects(submission_id)
                old_name_to_id: defaultdict[str, dict[str, str]] = defaultdict(dict)
                old_id_to_name: defaultdict[str, dict[str, str]] = defaultdict(dict)
                for obj in old_objects:
                    old_name_to_id[obj.objectType][obj.name] = obj.objectId
                    old_id_to_name[obj.objectType][obj.objectId] = obj.name

                def _is_old_object_by_name(_identifier: ObjectIdentifier) -> bool:
                    return _identifier.name in old_name_to_id.get(_identifier.object_type, {})

                def _is_old_object_by_id(_identifier: ObjectIdentifier) -> bool:
                    return _identifier.id in old_id_to_name.get(_identifier.object_type, {})

                def _get_old_id_by_name(_identifier: ObjectIdentifier) -> str | None:
                    return old_name_to_id.get(_identifier.object_type, {}).get(_identifier.name)

                def _get_old_name_by_id(_identifier: ObjectIdentifier) -> str | None:
                    return old_id_to_name.get(_identifier.object_type, {}).get(_identifier.id)

                # Find deleted objects.
                identifier_names = {identifier.name for identifier in identifiers}
                identifier_ids = {identifier.id for identifier in identifiers}
                deleted_objects = [
                    obj
                    for obj in old_objects
                    if obj.name not in identifier_names and obj.objectId not in identifier_ids
                ]

                # Find old objects and assign ids.
                # Find new objects.
                for identifier in identifiers:
                    if _is_old_object_by_name(identifier):
                        # Updated object: name found for object type in existing submission.
                        old_id = _get_old_id_by_name(identifier)
                        if identifier.id and identifier.id != old_id:
                            errors.append(
                                f"Accession conflict in metadata object '{identifier.object_type}'. "
                                f"Expected: '{old_id}', Found: '{identifier.id}'"
                            )
                        else:
                            # Make sure the identifier and all references have name and id.
                            identifier.id = old_id
                            processor.set_object_id(identifier)
                            updated_object_identifiers.append(identifier)
                    elif _is_old_object_by_id(identifier):
                        # Updated object: id found for object type in existing submission.
                        old_name = _get_old_name_by_id(identifier)
                        if identifier.name and identifier.name != old_name:
                            errors.append(
                                f"Name conflict in metadata object '{identifier.object_type}'. "
                                f"Expected: '{old_name}', Found: '{identifier.name}'"
                            )
                        else:
                            # Make sure the identifier and all references have name and id.
                            identifier.name = old_name
                            processor.set_object_id(identifier)
                            updated_object_identifiers.append(identifier)
                    else:
                        if identifier.id is not None:
                            errors.append(
                                f"Unexpected accession {identifier.id} in metadata object '{identifier.schema_type}'."
                            )
                        # New object.
                        new_object_identifiers.append(identifier)

                if not self._supports_references:
                    # Check that no metadata objects are referenced outside the submission.
                    for ref_identifier in processor.get_object_references():
                        if ref_identifier.id is not None:
                            error = True
                            for identifier in identifiers:
                                if ref_identifier.id == identifier.id:
                                    error = False
                                    break
                            if error:
                                errors.append(
                                    f"Unsupported reference to '{ref_identifier.schema_type}' "
                                    f"metadata object '{ref_identifier.id}' outside the submission."
                                )

                if errors:
                    raise UserErrors(errors)

            if processor:
                # Assign metadata object accessions.
                for identifier in new_object_identifiers:
                    identifier.id = generate_accession(self._workflow, identifier.object_type)
                    processor.set_object_id(identifier)

                # Check that all metadata object references have accessions.
                for identifier in processor.get_references_without_ids():
                    errors.append(f"Unknown '{identifier.schema_type}' metadata object '{identifier.id}' reference")

            # Prepare submission document.
            old_submission = await self._submission_service.get_submission_by_id(submission_id)
            submission = self.prepare_update_submission(old_submission)

            # Prepare submission files.
            files = self.prepare_files(submission_id)

            # Create and save submission and metadata objects within one transaction.
            async with transaction(self._session_factory):

                # Update submission.
                await self._submission_service.update_submission(submission_id, to_json_dict(submission))

                # Get saved submission.
                submission = Submission.model_validate(
                    await self._submission_service.get_submission_by_id(submission_id)
                )

                if processor:
                    # Add new metadata objects.
                    for identifier in new_object_identifiers:
                        object_processor = await self._get_object_processor(identifier, processor)
                        await self._add_object(project_id, submission_id, identifier, object_processor)

                    # Update existing metadata objects.
                    for identifier in updated_object_identifiers:
                        object_processor = await self._get_object_processor(identifier, processor)
                        await self._update_object(identifier, object_processor)

                    # Delete removed metadata objects.
                    for obj in deleted_objects:
                        await self._object_service.delete_object_by_id(obj.objectId)

                # Replace files.
                async for file in self._file_service.get_files(submission_id=submission_id):
                    await self._file_service.delete_file_by_id(file.fileId)
                for file in files:
                    await self._file_service.add_file(file, self._workflow)

        except ValidationError as e:
            # Preserve Pydantic validation error.
            raise e
        except Exception as e:
            errors.append(str(e))
            raise UserErrors(errors) from e

        return submission

    @staticmethod
    async def _get_object_processor(identifier: ObjectIdentifier, processor: DocumentsProcessor) -> ObjectProcessor:
        """
        Get object processor.

        :param identifier: The metadata object identifier.
        :param processor: The metadata documents processor.
        :return: The object processor.
        """

        object_processor = processor.get_object_processor(identifier.schema_type, identifier.root_path, identifier.name)
        return object_processor

    async def _add_object(
        self, project_id: str, submission_id: str, identifier: ObjectIdentifier, processor: ObjectProcessor
    ) -> None:
        """
        Add metadata object to the database.

        :param project_id: The project id.
        :param submission_id: The submission id.
        :param identifier: The metadata object identifier.
        :param processor: The metadata object processor.
        """

        if isinstance(processor, XmlObjectProcessor):
            saved_object_id = await self._object_service.add_object(
                project_id,
                submission_id,
                identifier.name,
                identifier.object_type,
                self._workflow,
                object_id=identifier.id,
                title=processor.get_object_title(),
                description=processor.get_object_description(),
                xml_document=processor.write_xml(processor.xml),
            )
            if saved_object_id != identifier.id:
                raise SystemException("Failed to save generated object id")
        else:
            raise SystemException("Unsupported object processor")

    async def _update_object(self, identifier: ObjectIdentifier, processor: ObjectProcessor) -> None:
        """
        Update metadata object in the database.

        :param project_id: The project id.
        :param submission_id: The submission id.
        :param identifier: The metadata object identifier.
        :param processor: The metadata object processor.
        """

        if isinstance(processor, XmlObjectProcessor):
            await self._object_service.update_object(
                identifier.id,
                title=processor.get_object_title(),
                description=processor.get_object_description(),
                xml_document=processor.write_xml(processor.xml),
            )
        else:
            raise SystemException("Unsupported object processor")
