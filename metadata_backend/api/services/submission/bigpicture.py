"""Service for processing BigPicture submissions."""

from typing import override

from ....database.postgres.services.file import FileService
from ....database.postgres.services.object import ObjectService
from ....database.postgres.services.submission import SubmissionService
from ...exceptions import UserException
from ...models.datacite import DataCiteMetadata
from ...models.models import File
from ...models.submission import Rems, Submission, SubmissionMetadata, SubmissionWorkflow
from ...processors.xml.bigpicture import (
    BP_ANNOTATION_PATH,
    BP_ANNOTATION_SCHEMA,
    BP_DATASET_OBJECT_TYPE,
    BP_DATASET_PATH,
    BP_DATASET_SCHEMA,
    BP_FULL_SUBMISSION_XML_OBJECT_CONFIG,
    BP_IMAGE_PATH,
    BP_IMAGE_SCHEMA,
    BP_REMS_PATH,
    BP_REMS_SCHEMA,
)
from ...processors.xml.datacite import read_datacite_xml
from ...processors.xml.processors import XmlStringDocumentsProcessor
from ..project import ProjectService
from .submission import ObjectSubmission, ObjectSubmissionService

# mypy: disable_error_code = misc


DATACITE_FILE = "datacite.xml"
BP_FILES = [
    "annotation.xml",
    "dataset.xml",
    "image.xml",
    "landing_page.xml",
    "observation.xml",
    "observer.xml",
    "organisation.xml",
    "policy.xml",
    "rems.xml",
    "sample.xml",
    "staining.xml",
]


class BigPictureObjectSubmissionService(ObjectSubmissionService):
    """Service for processing BigPicture submissions."""

    def __init__(
        self,
        project_service: ProjectService,
        submission_service: SubmissionService,
        object_service: ObjectService,
        file_service: FileService,
    ) -> None:
        """
        Service for processing BigPicture submissions.

        :param project_service: The Postgres project service.
        :param submission_service: The Postgres submission service.
        :param object_service: The Postgres object service.
        :param file_service: The Postgres file service.
        :param session_factory: The SQLAlchemy session factory.
        """

        self._datacite: DataCiteMetadata | None = None
        self._processor: XmlStringDocumentsProcessor | None = None

        super().__init__(
            project_service=project_service,
            submission_service=submission_service,
            object_service=object_service,
            file_service=file_service,
            workflow=SubmissionWorkflow.BP,
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

        processor, datacite = BigPictureObjectSubmissionService._create_processor(objects)
        self._processor = processor
        self._datacite = datacite
        return self._processor

    @staticmethod
    def _create_processor(objects: list[ObjectSubmission]) -> tuple[XmlStringDocumentsProcessor, DataCiteMetadata]:
        """
        Return XML documents processor for BigPicture XMLs (excl. DataCite XML) and datacite metadata from DataCite XML.

        :param objects: The metadata object documents.
        :return: a tuple containing the XML documents processor and the DataCite metadata
        """

        datacite_object, bp_objects = BigPictureObjectSubmissionService._get_objects(objects)

        # Read DataCite XML.
        datacite = None
        if datacite_object:
            datacite = read_datacite_xml(datacite_object.document)

        # Create processor for BigPicture XMLs.
        processor = XmlStringDocumentsProcessor(BP_FULL_SUBMISSION_XML_OBJECT_CONFIG, [o.document for o in bp_objects])
        return processor, datacite

    @override
    def assign_submission_accession(self) -> str | None:
        """
        Assign submission accession number.

        :return: the submission id.
        """

        # Assign metadata object accessions.
        for identifier in self._processor.get_object_identifiers():
            if identifier.object_type == BP_DATASET_OBJECT_TYPE:
                # Use dataset id as the submission accession.
                return identifier.id

        return None

    @override
    def prepare_create_submission(self, project_id: str, submission_id: str) -> Submission:
        """
        Prepare submission document.

        :param project_id: The project id.
        :param submission_id: The submission id.
        :return: The submission document.
        """

        # The BP XML processor guarantees that we have one dataset and rems metadata object.
        dataset_identifiers = self._processor.get_object_identifiers(BP_DATASET_SCHEMA)
        rems_identifiers = self._processor.get_object_identifiers(BP_REMS_SCHEMA)

        # Get dataset and rems metadata object processor.
        dataset_processor = self._processor.get_object_processor(
            BP_DATASET_SCHEMA, BP_DATASET_PATH, dataset_identifiers[0].name
        )
        rems_processor = self._processor.get_object_processor(BP_REMS_SCHEMA, BP_REMS_PATH, rems_identifiers[0].name)

        # Use dataset short name as the submission name.
        name = dataset_processor.get_xml_node_value("./SHORT_NAME")

        # Get REMS.
        workflow_id = int(rems_processor.get_xml_node_value("./WORKFLOW_ID"))
        organization_id = rems_processor.get_xml_node_value("./ORGANISATION_ID")

        return Submission(
            projectId=project_id,
            submissionId=submission_id,
            name=name,
            title=dataset_processor.get_object_title(),
            description=dataset_processor.get_object_description(),
            workflow=SubmissionWorkflow.BP,
            rems=Rems(
                workflowId=workflow_id,
                organizationId=organization_id,
            ),
            metadata=SubmissionMetadata.from_datacite(self._datacite) if self._datacite else None,
        )

    @override
    def prepare_files(self, submission_id: str) -> list[File]:
        """
        Prepare submission files.

        :param submission_id: The submission id.
        :return: The submission files.
        """

        files = []

        image_processors = self._processor.get_xml_object_processors(BP_IMAGE_SCHEMA, BP_IMAGE_PATH)
        annotation_processors = self._processor.get_xml_object_processors(BP_ANNOTATION_SCHEMA, BP_ANNOTATION_PATH)

        for image_processor in image_processors:
            object_id = image_processor.get_xml_object_identifier().id
            xml = image_processor.xml
            for file_elem in xml.xpath("/IMAGE/FILES/FILE"):
                files.append(
                    File(
                        submissionId=submission_id,
                        objectId=object_id,
                        path=file_elem.get("filename"),
                        checksumMethod=file_elem.get("checksum_method"),
                        unencryptedChecksum=file_elem.get("unencrypted_checksum"),
                        encryptedChecksum=file_elem.get("checksum"),
                    )
                )

        for annotation_processor in annotation_processors:
            object_id = annotation_processor.get_xml_object_identifier().id
            xml = annotation_processor.xml
            for file_elem in xml.xpath("/ANNOTATION/FILES/FILE"):
                files.append(
                    File(
                        submissionId=submission_id,
                        objectId=object_id,
                        path=file_elem.get("filename"),
                        checksumMethod=file_elem.get("checksum_method"),
                        unencryptedChecksum=file_elem.get("unencrypted_checksum"),
                        encryptedChecksum=file_elem.get("checksum"),
                    )
                )

        return files

    @staticmethod
    def _get_objects(objects: list[ObjectSubmission]) -> tuple[ObjectSubmission | None, list[ObjectSubmission]]:
        """
        Separate Datacite metadata object from BigPicture metadata objects.

        :param objects: The metadata object documents.
        :return: tuple of DataCite metadata object and BigPicture metadata objects.
        """
        datacite_object = None
        bp_objects = []

        filenames = BP_FILES + [DATACITE_FILE]
        filenames_seen = set()

        for obj in objects:
            filename_lower = obj.filename.lower()

            if filename_lower not in (f.lower() for f in filenames):
                raise UserException(f"Invalid file name: {obj.filename}. Expected file names: {', '.join(filenames)}.")

            if filename_lower in filenames_seen:
                raise ValueError(f"Duplicate file name: {obj.filename}")

            filenames_seen.add(filename_lower)

            if filename_lower == DATACITE_FILE.lower():
                datacite_object = obj
            else:
                bp_objects.append(obj)

        return datacite_object, bp_objects
