"""Service for processing Bigpicture submissions."""

# TODO: Make these modules a bigpicture package, to drop the prefix and split further.

from pathlib import Path
from typing import override

from lxml.etree import Element
from lxml.etree import _ElementTree as ElementTree  # noqa

from ....database.postgres.services.file import FileService
from ....database.postgres.services.object import ObjectService
from ....database.postgres.services.submission import SubmissionService
from ...exceptions import SystemException, UserException
from ...models.datacite import DataCiteMetadata
from ...models.models import File
from ...models.submission import Rems, Submission, SubmissionMetadata, SubmissionWorkflow
from ...processors.xml.bigpicture import (
    BP_ANNOTATION_OBJECT_TYPE,
    BP_ANNOTATION_PATH,
    BP_ANNOTATION_SCHEMA,
    BP_DATASET_OBJECT_TYPE,
    BP_DATASET_PATH,
    BP_DATASET_SCHEMA,
    BP_IMAGE_OBJECT_TYPE,
    BP_IMAGE_PATH,
    BP_IMAGE_SCHEMA,
    BP_OBSERVATION_OBJECT_TYPE,
    BP_OBSERVATION_PATH,
    BP_OBSERVATION_SCHEMA,
    BP_OBSERVER_OBJECT_TYPE,
    BP_OBSERVER_PATH,
    BP_OBSERVER_SCHEMA,
    BP_REMS_PATH,
    BP_REMS_SCHEMA,
    BP_XML_OBJECT_CONFIG,
)
from ...processors.xml.datacite import DATACITE_OBJECT_TYPE, read_datacite_xml
from ...processors.xml.processors import XmlDocumentsProcessor, XmlStringDocumentsProcessor
from ..accession import generate_bp_accession
from ..project import ProjectService
from .bigpicture_policy import (
    create_policy_license,
    is_clinical_policy,
    normalise_policy_attributes,
    policy_processor,
    validate_policy_attributes,
)
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


DATACITE_OBJECT_TITLE = "DataCite"
DATACITE_OBJECT_DESCRIPTION = "DataCite"


def validate_bigpicture_documents(processor: XmlDocumentsProcessor) -> None:
    """
    Validate Bigpicture XML documents beyond the XML Schema and reference validation.

    XML attributes and validated here.

    The validation may change the XMLs to make them valid.

    :param processor: The XML documents processor.
    :raises UserException: if the documents do not pass validation.
    """

    # Check mandatory constraints first to report missing metadata objects.
    check_mandatory_constraints(processor)

    # Find the policy once, rather than in each of the checks below.
    policy = policy_processor(processor)

    # Check policy type.
    is_clinical_policy(policy)

    # Normalise attribute tags and values.
    normalise_policy_attributes(policy)

    # Validate attribute tags and values.
    validate_policy_attributes(policy)

    # Check that the REMS license can be created from the policy.
    create_policy_license(policy)


def check_mandatory_constraints(processor: XmlDocumentsProcessor) -> None:
    """
    Check mandatory constraints specified in the Bigpicture metadata
    standard document v2.0.0-2 not enforced by the XML Schemas.
    Raises a ValueError if a mandatory constraint check fails.

    :param processor: The XML documents processor.
    """

    max_reported_objects = 10

    _check_mandatory_constraint_5(processor)
    _check_mandatory_constraint_7(processor, max_reported_objects)


def _check_mandatory_constraint_5(processor: XmlDocumentsProcessor) -> None:
    """
    Check mandatory constraint 5.

    Each Image, Annotation and Observation must be referenced by the Dataset Entity.

    :param processor: The XML documents processor.
    """

    # Get images.
    images = {}
    for image_processor in processor.get_xml_object_processors(BP_IMAGE_SCHEMA, BP_IMAGE_PATH):
        identifier = image_processor.get_xml_object_identifier()
        images[identifier.name] = identifier.id

    # Get annotations.
    annotations = {}
    for annotation_processor in processor.get_xml_object_processors(BP_ANNOTATION_SCHEMA, BP_ANNOTATION_PATH):
        identifier = annotation_processor.get_xml_object_identifier()
        annotations[identifier.name] = identifier.id

    # Get observations.
    observations = {}
    for observation_processor in processor.get_xml_object_processors(BP_OBSERVATION_SCHEMA, BP_OBSERVATION_PATH):
        identifier = observation_processor.get_xml_object_identifier()
        observations[identifier.name] = identifier.id

    # Get image, annotation, observation references in dataset.
    image_refs = set()
    annotation_refs = set()
    observation_refs = set()

    # The BP XML processor guarantees that we have one dataset object.
    dataset_identifiers = processor.get_object_identifiers(BP_DATASET_SCHEMA)
    dataset_processor = processor.get_object_processor(BP_DATASET_SCHEMA, BP_DATASET_PATH, dataset_identifiers[0].name)

    for ref in dataset_processor.get_object_references():
        if ref.object_type == BP_IMAGE_OBJECT_TYPE:
            image_refs.add(ref.name)
        if ref.object_type == BP_ANNOTATION_OBJECT_TYPE:
            annotation_refs.add(ref.name)
        if ref.object_type == BP_OBSERVATION_OBJECT_TYPE:
            observation_refs.add(ref.name)

    # Add missing references to dataset.

    dataset_xml = dataset_processor.xml
    dataset_element = dataset_xml.getroot()

    def insert_after(new_element: Element, prev_element: list[str]) -> None:
        """
        Insert new element after the last element in the prioritised element list
        to maintain the required sequence order.
        """
        for e in prev_element:
            existing_element = dataset_element.findall(e)
            if existing_element:
                dataset_element.insert(dataset_element.index(existing_element[-1]) + 1, new_element)
                return

        raise SystemException(f"Failed to insert missing element to dataset XML: {new_element.tag}")

    def add_image_ref(alias: str) -> None:
        insert_after(
            Element("IMAGE_REF", alias=alias),
            ["IMAGE_REF", "DATASET_TYPE", "DATASET_OWNER_CONTACT_EMAIL", "METADATA_STANDARD"],
        )

    def add_annotation_ref(alias: str) -> None:
        insert_after(
            Element("ANNOTATION_REF", alias=alias),
            ["ANNOTATION_REF", "IMAGE_REF", "DATASET_TYPE", "DATASET_OWNER_CONTACT_EMAIL", "METADATA_STANDARD"],
        )

    def add_observation_ref(alias: str) -> None:
        insert_after(
            Element("OBSERVATION_REF", alias=alias),
            [
                "OBSERVATION_REF",
                "ANNOTATION_REF",
                "IMAGE_REF",
                "DATASET_TYPE",
                "DATASET_OWNER_CONTACT_EMAIL",
                "METADATA_STANDARD",
            ],
        )

    # Add missing references
    for name in images.keys() - image_refs:
        add_image_ref(name)
    for name in annotations.keys() - annotation_refs:
        add_annotation_ref(name)
    for name in observations.keys() - observation_refs:
        add_observation_ref(name)


def _check_mandatory_constraint_7(processor: XmlDocumentsProcessor, max_reported_objects: int) -> None:
    """
    Check mandatory constraint 7.

    Any given Observer must be referenced by at least one Observation.
    :param processor: The XML documents processor.
    :param max_reported_objects: The maximum number of reported objects
    """

    observer = set()
    for observation_processor in processor.get_xml_object_processors(BP_OBSERVATION_SCHEMA, BP_OBSERVATION_PATH):
        for ref in observation_processor.get_object_references():
            if ref.object_type == BP_OBSERVER_OBJECT_TYPE:
                observer.add(ref.name)

    # Find observers not associated with observations

    observer_no_observation = set()

    for observer_processor in processor.get_xml_object_processors(BP_OBSERVER_SCHEMA, BP_OBSERVER_PATH):
        observer_name = observer_processor.get_xml_object_identifier().name
        if observer_name not in observer:
            observer_no_observation.add(observer_name)

    if observer_no_observation:
        raise UserException(
            f"{len(observer_no_observation)} observers are not associated with observations. "
            f"Examples: {', '.join(list(observer)[:max_reported_objects])}"
        )


class BigpictureObjectSubmissionService(ObjectSubmissionService):
    """Service for processing Bigpicture submissions."""

    def __init__(
        self,
        project_service: ProjectService,
        submission_service: SubmissionService,
        object_service: ObjectService,
        file_service: FileService,
    ) -> None:
        """
        Service for processing Bigpicture submissions.

        :param project_service: The Postgres project service.
        :param submission_service: The Postgres submission service.
        :param object_service: The Postgres object service.
        :param file_service: The Postgres file service.
        """

        self._datacite: DataCiteMetadata | None = None
        self._datacite_xml: ElementTree | None = None
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

        processor, datacite, datacite_xml = BigpictureObjectSubmissionService._create_processor(objects)
        self._processor = processor
        self._datacite = datacite
        self._datacite_xml = datacite_xml
        return self._processor

    @staticmethod
    def _create_processor(
        objects: list[ObjectSubmission],
    ) -> tuple[XmlStringDocumentsProcessor, DataCiteMetadata | None, ElementTree | None]:
        """
        Return XML documents processor for Bigpicture XMLs (excl. DataCite XML),
        datacite metadata, and the DataCite XML.

        :param objects: The metadata object documents.
        :return: a tuple containing the XML documents processor (excl. DataCite XML),
        datacite metadata, and the DataCite XML.
        """

        datacite_object, bp_objects = BigpictureObjectSubmissionService._get_objects(objects)

        # Read DataCite XML.
        datacite = None
        datacite_xml = None
        if datacite_object:
            datacite, datacite_xml = read_datacite_xml(datacite_object.document)

        # Create processor for Bigpicture XMLs.
        processor = XmlStringDocumentsProcessor(BP_XML_OBJECT_CONFIG, [o.document for o in bp_objects])
        return processor, datacite, datacite_xml

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
    def validate_documents(self) -> None:
        """
        Validate XML documents in addition to the XML schema snd reference
        validation.

        The validation may change the XMLs to make the valid.
        """

        validate_bigpicture_documents(self._processor)

    @override
    def prepare_create_submission(self, project_id: str, submission_id: str) -> Submission:
        """
        Prepare submission document.

        :param project_id: The project id.
        :param submission_id: The submission id.
        :return: The submission document.
        """

        # The BP XML processor guarantees that we have one dataset, rems and policy metadata object.
        dataset_identifiers = self._processor.get_object_identifiers(BP_DATASET_SCHEMA)
        rems_identifiers = self._processor.get_object_identifiers(BP_REMS_SCHEMA)

        # Get dataset, rems and policy metadata object processor.
        dataset_processor = self._processor.get_object_processor(
            BP_DATASET_SCHEMA, BP_DATASET_PATH, dataset_identifiers[0].name
        )
        rems_processor = self._processor.get_object_processor(BP_REMS_SCHEMA, BP_REMS_PATH, rems_identifiers[0].name)

        # Use dataset alias as the submission name. The alias is the dataset's
        # unique identifier per the Bigpicture Metadata Standard, unlike SHORT_NAME.
        name = dataset_identifiers[0].name

        # Get REMS.
        workflow_id = rems_processor.get_xml_node_value("./WORKFLOW_ID")
        if workflow_id is None:
            raise UserException("Missing REMS workflow id.")
        try:
            int(workflow_id)
        except Exception:
            raise UserException(f"REMS workflow id '{workflow_id}' must be an integer.")

        organization_id = rems_processor.get_xml_node_value("./ORGANISATION_ID")

        return Submission(
            projectId=project_id,
            submissionId=submission_id,
            name=name,
            title=dataset_processor.get_object_title(),
            description=dataset_processor.get_object_description(),
            workflow=SubmissionWorkflow.BP,
            rems=Rems(
                workflowId=int(workflow_id),
                organizationId=organization_id,
            ),
            metadata=SubmissionMetadata.from_datacite(self._datacite) if self._datacite else None,
        )

    @override
    def prepare_update_submission(self, old_submission: Submission) -> Submission:
        """
        Prepare submission document.

        :param old_submission: The existing submission.
        :return: The submission document.
        """

        return self.prepare_create_submission(old_submission.projectId, old_submission.submissionId)

    @staticmethod
    def _prepare_file_path(file_path: str) -> str:
        """Add .c4gh" suffix to the file path if it is missing.

        :param file_path: the file path.
        :return: the file path with .c4gh suffix.
        """
        return file_path if file_path.endswith(".c4gh") else f"{file_path}.c4gh"

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
            root = xml.getroot()

            # Validate the image file paths and extensions
            alias = root.get("alias")
            for file_elem in xml.xpath("/IMAGE/FILES/FILE"):
                filename = self._prepare_file_path(file_elem.get("filename"))
                self.check_image_file_dir(alias, filename)
                dir_part, _, file_part = filename.rpartition("/")  # "IMAGES/IMAGE_{alias}", "/", "*.dcm.c4gh"
                if not file_part.removesuffix(".c4gh").endswith(".dcm"):
                    raise UserException(f"Image file '{filename}' must have a .dcm extension.")

                # User is expected to upload the image files to the S3 inbox using
                # the DATASET_{submission_id} path prefix where the submission_id is
                # the same as the newly generated dataset accession ID.
                files.append(
                    File(
                        submissionId=submission_id,
                        objectId=object_id,
                        path=f"DATASET_{submission_id}/{filename}",
                        checksumMethod=file_elem.get("checksum_method"),
                        unencryptedChecksum=file_elem.get("unencrypted_checksum"),
                        encryptedChecksum=file_elem.get("checksum"),
                    )
                )

        for annotation_processor in annotation_processors:
            object_id = annotation_processor.get_xml_object_identifier().id
            xml = annotation_processor.xml

            # Validate the annotation file paths and extensions
            for file_elem in xml.xpath("/ANNOTATION/FILES/FILE"):
                filename = self._prepare_file_path(file_elem.get("filename"))
                dir_part = str(Path(filename).parent)
                if dir_part != "ANNOTATIONS":
                    raise UserException(f"Annotation file '{filename}' must be in directory 'ANNOTATIONS'.")
                files.append(
                    File(
                        submissionId=submission_id,
                        objectId=object_id,
                        path=f"DATASET_{submission_id}/{filename}",
                        checksumMethod=file_elem.get("checksum_method"),
                        unencryptedChecksum=file_elem.get("unencrypted_checksum"),
                        encryptedChecksum=file_elem.get("checksum"),
                    )
                )

        return files

    @staticmethod
    def _get_objects(objects: list[ObjectSubmission]) -> tuple[ObjectSubmission | None, list[ObjectSubmission]]:
        """
        Separate Datacite metadata object from Bigpicture metadata objects.

        :param objects: The metadata object documents.
        :return: tuple of DataCite metadata object and Bigpicture metadata objects.
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

    @override
    async def create(self, user_id: str, project_id: str, objects: list[ObjectSubmission]) -> Submission:
        """
        Create a new submission.

        :param user_id: The user id.
        :param project_id: The project id.
        :param objects: The metadata object documents.
        :returns: The submission document.
        :raises UserErrors: If case of any user errors.
        """

        # Store all XMLs except DataCite XML.
        submission = await super().create(user_id, project_id, objects)

        # Store DataCite XML.
        if self._datacite_xml is not None:
            # Add DataCite XML.
            datacite_id = generate_bp_accession(DATACITE_OBJECT_TYPE)
            await self._add_object(
                project_id,
                submission.submissionId,
                datacite_id,
                # Use DataCite accession as the name. The name must be unique
                # and DataCite XML does not have one.
                DATACITE_OBJECT_TYPE,
                datacite_id,
                DATACITE_OBJECT_TITLE,
                DATACITE_OBJECT_DESCRIPTION,
                self._datacite_xml,
            )

        return submission

    @override
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
        # Update all other XMLs except DataCite XML.
        submission = await super().update(user_id, project_id, submission_id, objects)

        # Get datacite object if it exists.
        datacite_object = None
        for obj in await self._object_service.get_objects(submission_id, DATACITE_OBJECT_TYPE):
            datacite_object = obj

        # Update DataCite XML.
        if self._datacite_xml is not None:
            if datacite_object is not None:
                # Update DataCite XML.
                await self._update_object(
                    datacite_object.objectId,
                    DATACITE_OBJECT_TITLE,
                    DATACITE_OBJECT_DESCRIPTION,
                    self._datacite_xml,
                )
            else:
                # Add DataCite XML.
                datacite_id = generate_bp_accession(DATACITE_OBJECT_TYPE)
                await self._add_object(
                    project_id,
                    submission_id,
                    # Use DataCite accession as the name. The name must be unique
                    # and DataCite XML does not have one.
                    datacite_id,
                    DATACITE_OBJECT_TYPE,
                    datacite_id,
                    DATACITE_OBJECT_TITLE,
                    DATACITE_OBJECT_DESCRIPTION,
                    self._datacite_xml,
                )
        elif datacite_object is not None:
            # Delete DataCite XML if it exists.
            await self._delete_object(datacite_object.objectId)

        return submission

    @staticmethod
    def check_image_file_dir(alias: str, image_file_path: str) -> None:
        """
        Check if the image file is in the correct directory.

        :param alias: The image metadata object alias.
        :param image_file_path: The image file path.
        :raises UserException: If the image file is not in the correct directory.
        """
        alias = alias.removeprefix("IMAGE_")  # Alias may contain IMAGE_ prefix.
        expected_dir = f"IMAGES/IMAGE_{alias}"
        dir_part, _, _ = image_file_path.rpartition("/")
        if dir_part != expected_dir:
            raise UserException(f"Image file '{image_file_path}' must be in directory '{expected_dir}'.")
