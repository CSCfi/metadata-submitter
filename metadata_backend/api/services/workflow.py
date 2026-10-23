"""Submission workflow profiles.

A workflow profile holds the workflow-specific behaviour of a submission.
"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, ClassVar, Iterable, Sequence, override

from ...helpers.logger import LOG
from ..exceptions import UserException
from ..models.models import File, Registration
from ..models.submission import Rems, Submission, SubmissionWorkflow
from ..processors.xml.bigpicture import BP_POLICY_OBJECT_TYPE, get_bp_default_dataset_dir
from ..processors.xml.datacite import DATACITE_OBJECT_TYPE, DATACITE_SCHEMA
from ..processors.xml.fega import FEGA_XML_OBJECT_CONFIG
from ..processors.xml.models import XmlObjectConfig
from ..processors.xml.processors import XmlObjectProcessor
from .bigpicture import generate_bp_metadata_xmls, upload_bp_metadata_xmls
from .submission.bigpicture import BigpictureObjectSubmissionService
from .submission.bigpicture_import import BigpictureObjectImportService
from .submission.bigpicture_policy import is_clinical_policy
from .submission.bigpicture_version import get_bp_xml_object_config
from .submission.sensitive_data import SensitiveDataObjectSubmissionService
from .submission.submission import ObjectSubmissionService

if TYPE_CHECKING:
    # Only needed for type annotations.
    from ..handlers.restapi import RESTAPIServiceHandlers, RESTAPIServices


class SubmissionWorkflowProfile(ABC):
    """Workflow-specific behaviour of a submission."""

    workflow: ClassVar[SubmissionWorkflow]

    # Whether the submission must have DataCite metadata, from which its DOI is registered, to be published.
    requires_datacite: ClassVar[bool] = False

    @abstractmethod
    def object_submission_service(self, services: RESTAPIServices) -> ObjectSubmissionService:
        """
        Get the service that creates and updates submissions from submitted documents.

        :param services: The REST API services.
        :returns: The object submission service.
        """

    def object_import_service(
        self, services: RESTAPIServices, handlers: RESTAPIServiceHandlers
    ) -> ObjectSubmissionService:
        """
        Get the service that creates submissions from datasets accessioned and ingested outside SD Submit.

        :param services: The REST API services.
        :param handlers: The REST API service handlers.
        :returns: The object import service.
        :raises UserException: If the workflow does not support imports.
        """
        raise UserException(f"Import is not supported for workflow: {self.workflow.value}")

    @abstractmethod
    def object_types(
        self, submission: Submission, *, object_type: str | None = None, schema_type: str | None = None
    ) -> Sequence[str] | None:
        """
        Get the requested metadata object type(s).

        :param submission: The submission.
        :param object_type: The object type.
        :param schema_type: The schema type.
        :returns: The object types, or None if neither object type of scheme type was requested.
        :raises UserException: If the object type or the schema type is unknown.
        """

    @abstractmethod
    async def prepare_publish(
        self, services: RESTAPIServices, submission_id: str, user_id: str, jwt: str | None
    ) -> None:
        """
        Prepare the submission data and metadata files for publishing.

        Called before the submission is registered with external services, so that a submission that
        can't be published fails before any registration is made.

        :param services: The REST API services.
        :param submission_id: The submission id.
        :param user_id: The user id.
        :param jwt: The user's OIDC access token.
        """

    @abstractmethod
    async def finish_publish(
        self, services: RESTAPIServices, submission_id: str, user_id: str, jwt: str | None
    ) -> None:
        """
        Finish publishing the submission data and metadata files.

        Called after the submission is registered with external services, so that the registration
        identifiers and URLs are available.

        :param services: The REST API services.
        :param submission_id: The submission id.
        :param user_id: The user id.
        :param jwt: The user's OIDC access token.
        """

    @abstractmethod
    def registration_title(self, submission: Submission, rems: Rems) -> str:
        """
        Get the registration title, used as the DataCite, Metax and REMS catalogue item title.

        :param submission: The submission.
        :param rems: The REMS metadata.
        :returns: The registration title.
        """

    @abstractmethod
    def discovery_id(self, submission: Submission, registration: Registration) -> str:
        """
        Get the id of the submission in its discovery URL.

        :param submission: The submission.
        :param registration: The registration.
        :returns: The discovery id.
        """

    @abstractmethod
    def rems_resource_id(self, submission: Submission, registration: Registration) -> str:
        """
        Get the REMS resource id.

        :param submission: The submission.
        :param registration: The registration.
        :returns: The REMS resource id.
        """

    async def is_published_to_rems(self, services: RESTAPIServices, submission: Submission) -> bool:
        """
        Whether the submission is published to REMS.

        :param services: The REST API services.
        :param submission: The submission.
        :returns: True if the submission is published to REMS.
        """
        return True


class XmlSubmissionWorkflowProfile(SubmissionWorkflowProfile):
    """Behaviour of a workflow whose metadata is submitted as XML objects."""

    # Whether the submission may have DataCite metadata objects in addition to the XML metadata objects.
    has_datacite_objects: ClassVar[bool] = False

    @abstractmethod
    def xml_config(self, submission: Submission) -> XmlObjectConfig:
        """
        Get the XML processing configuration of the submission.

        :param submission: The submission.
        :returns: The XML object configuration.
        """

    @override
    def object_types(
        self, submission: Submission, *, object_type: str | None = None, schema_type: str | None = None
    ) -> Sequence[str] | None:
        config = self.xml_config(submission)
        if object_type is not None:
            known_object_types = {p.object_type for p in config.object_paths}
            if self.has_datacite_objects:
                known_object_types.add(DATACITE_OBJECT_TYPE)
            if object_type not in known_object_types:
                raise UserException(f"Unknown object type: {object_type}")
            return [object_type]
        if schema_type is not None:
            if schema_type == DATACITE_SCHEMA and self.has_datacite_objects:
                return [DATACITE_OBJECT_TYPE]
            try:
                return config.get_object_types(schema_type)
            except ValueError as e:
                raise UserException(f"Unknown schema type: {schema_type}") from e
        return None


class SDSubmissionWorkflow(SubmissionWorkflowProfile):
    """Sensitive data (SD) workflow."""

    workflow = SubmissionWorkflow.SD
    requires_datacite = True

    @override
    def object_submission_service(self, services: RESTAPIServices) -> ObjectSubmissionService:
        return SensitiveDataObjectSubmissionService(
            services.project, services.submission, services.object, services.file
        )

    @override
    def object_types(
        self, submission: Submission, *, object_type: str | None = None, schema_type: str | None = None
    ) -> Sequence[str] | None:
        # SD submissions have no metadata objects.
        if object_type is not None:
            raise UserException(f"Unknown object type: {object_type}")
        if schema_type is not None:
            raise UserException(f"Unknown schema type: {schema_type}")
        return None

    @override
    async def prepare_publish(
        self, services: RESTAPIServices, submission_id: str, user_id: str, jwt: str | None
    ) -> None:
        """Add all files from the linked bucket to the submission and validate at least one file exists."""
        bucket = await services.submission.get_bucket(submission_id)
        if not bucket:
            raise UserException(f"Submission '{submission_id}' is not linked to any bucket.")

        files = await services.file_provider.list_files_in_bucket(bucket)
        for file in files.root:
            # Check that we have not added the file already.
            # For now, accept that file bytes might have changed and some files
            # might have been removed if a call to this endpoint has failed before.
            if not await services.file.is_file_by_path(submission_id, file.path):
                await services.file.add_file(
                    File(submissionId=submission_id, path=file.path, bytes=file.bytes),
                    SubmissionWorkflow.SD,
                )

        # Check that the submission has at least one file.
        if await services.file.count_files(submission_id) == 0:
            raise UserException(f"Submission '{submission_id}' does not have any data files.")

    @override
    async def finish_publish(
        self, services: RESTAPIServices, submission_id: str, user_id: str, jwt: str | None
    ) -> None:
        """The SD ingest is done by an external service."""

    @override
    def registration_title(self, submission: Submission, rems: Rems) -> str:
        return submission.title

    @override
    def discovery_id(self, submission: Submission, registration: Registration) -> str:
        # Use Metax id if available. Otherwise use DOI, and if that is not available,
        # use the submission id.
        return registration.metaxId or registration.doi or submission.submissionId

    @override
    def rems_resource_id(self, submission: Submission, registration: Registration) -> str:
        # Use DOI as the REMS resource id.
        # If DOI is unavailable use submission id as the REMS resource id.
        return registration.doi if registration.doi is not None else submission.submissionId


class FegaSubmissionWorkflow(XmlSubmissionWorkflowProfile):
    """Federated EGA (FEGA) workflow. Submissions can be read but not created, updated or published."""

    workflow = SubmissionWorkflow.FEGA

    @override
    def xml_config(self, submission: Submission) -> XmlObjectConfig:
        return FEGA_XML_OBJECT_CONFIG

    @override
    def object_submission_service(self, services: RESTAPIServices) -> ObjectSubmissionService:
        raise UserException(f"Unsupported workflow: {self.workflow.value}")

    @override
    async def prepare_publish(
        self, services: RESTAPIServices, submission_id: str, user_id: str, jwt: str | None
    ) -> None:
        raise UserException(f"Unsupported workflow: {self.workflow.value}")

    @override
    async def finish_publish(
        self, services: RESTAPIServices, submission_id: str, user_id: str, jwt: str | None
    ) -> None:
        raise UserException(f"Unsupported workflow: {self.workflow.value}")

    @override
    def registration_title(self, submission: Submission, rems: Rems) -> str:
        raise UserException(f"Unsupported workflow: {self.workflow.value}")

    @override
    def discovery_id(self, submission: Submission, registration: Registration) -> str:
        raise UserException(f"Unsupported workflow: {self.workflow.value}")

    @override
    def rems_resource_id(self, submission: Submission, registration: Registration) -> str:
        raise UserException(f"Unsupported workflow: {self.workflow.value}")


class BigpictureSubmissionWorkflow(XmlSubmissionWorkflowProfile):
    """Bigpicture (BP) workflow."""

    workflow = SubmissionWorkflow.BP
    has_datacite_objects = True

    @override
    def xml_config(self, submission: Submission) -> XmlObjectConfig:
        return get_bp_xml_object_config(submission)

    @override
    def object_submission_service(self, services: RESTAPIServices) -> ObjectSubmissionService:
        return BigpictureObjectSubmissionService(services.project, services.submission, services.object, services.file)

    @override
    def object_import_service(
        self, services: RESTAPIServices, handlers: RESTAPIServiceHandlers
    ) -> ObjectSubmissionService:
        return BigpictureObjectImportService(
            services.project, services.submission, services.object, services.file, handlers.admin, handlers.rems
        )

    @override
    async def prepare_publish(
        self, services: RESTAPIServices, submission_id: str, user_id: str, jwt: str | None
    ) -> None:
        """Validate the metadata XMLs and check the data files in the SDA inbox.

        The metadata XMLs are uploaded only by finish_publish, after registration, so that the landing page
        XML has the DataCite and REMS URLs.
        """
        if not jwt:
            raise UserException("Missing OIDC access token in Authorization bearer header for SDA inbox upload.")

        # Generate the metadata XMLs to validate them, so that an invalid XML fails before registration.
        metadata_xml_paths = (await generate_bp_metadata_xmls(services, submission_id)).keys()

        # Check the files in the SDA inbox. Add uploaded thumbnails as submission files, and check that every
        # submission file references by the XMLs is in the inbox and that there are no unexpected files. Skipped
        # for an imported submission, whose data files and thumbnails have already been ingested.
        if not await services.submission.is_imported(submission_id):
            await self._check_files_for_publish(services, user_id, submission_id, metadata_xml_paths)

    @override
    async def finish_publish(
        self, services: RESTAPIServices, submission_id: str, user_id: str, jwt: str | None
    ) -> None:
        """Upload the metadata XMLs to the SDA inbox, with the registration's URLs in the landing page XML."""
        if not jwt:
            raise UserException("Missing OIDC access token in Authorization bearer header for SDA inbox upload.")
        await upload_bp_metadata_xmls(services, submission_id, user_id, jwt)

    async def _check_files_for_publish(
        self, services: RESTAPIServices, user_id: str, submission_id: str, metadata_xml_paths: Iterable[str]
    ) -> None:
        """Check files in the S3 inbox for Bigpicture submission and sync with submission files.

        :param services: The REST API services.
        :param user_id: The user id
        :param submission_id: The submission id
        :param metadata_xml_paths: The inbox paths of the metadata XMLs, which are uploaded after this check.
        """
        # Add any thumbnail files the user has uploaded to the inbox bucket for the submission as submission files.
        await self._add_thumbnail_files(services, submission_id, user_id)

        submission_files = [file async for file in services.file.get_files(submission_id=submission_id)]
        LOG.info("Found %d files in submission '%s'.", len(submission_files), submission_id)

        # Check that all submission files are present in the S3 inbox.
        missing_files = await services.file_provider.find_missing_files(user_id, submission_id, submission_files)
        if missing_files:
            missing_paths = ", ".join(sorted(missing_files))
            raise UserException(f"Submission files for '{submission_id}' are missing from the inbox: {missing_paths}.")

        # Check that the submission directory in the inbox doesn't have unexpected files anymore at this point.
        # The metadata XMLs are uploaded only after this check, so they are not submission files yet. A publish
        # that failed after uploading them leaves them in the inbox, so they are counted as expected here.
        # Otherwise a retry would be refused for unexpected files.
        metadata_xml_files = [File(submissionId=submission_id, path=path) for path in metadata_xml_paths]
        unexpected_files = await services.file_provider.find_orphaned_files(
            user_id, submission_id, submission_files + metadata_xml_files
        )
        if unexpected_files:
            unexpected_paths = ", ".join(sorted(unexpected_files))
            raise UserException(
                f"Unexpected files found in the inbox for submission '{submission_id}': {unexpected_paths}."
            )

    async def _add_thumbnail_files(self, services: RESTAPIServices, submission_id: str, user_id: str) -> None:
        """Discover thumbnail files from the inbox and add missing ones as submission files.

        :param services: The REST API services.
        :param submission_id: The submission id.
        :param user_id: The user id.
        """
        thumbnails_prefix = f"{get_bp_default_dataset_dir(submission_id)}/LANDING_PAGE/THUMBNAILS/"

        file_service = services.file
        file_provider_service = services.file_provider

        inbox_files = await file_provider_service.list_submission_inbox_files(user_id, submission_id)

        added = 0
        for inbox_file in inbox_files:
            file_path = inbox_file.inbox_path

            # Skip adding files that may already be added to the submission.
            if await file_service.is_file_by_path(submission_id, file_path):
                continue

            # Thumbnail files are expected to be in the LANDING_PAGE/THUMBNAILS directory AND have .jpg.c4gh extension
            if file_path.startswith(thumbnails_prefix) and file_path.lower().endswith(".jpg.c4gh"):
                submission_file = File(submissionId=submission_id, path=file_path)
                await file_service.add_file(submission_file, SubmissionWorkflow.BP)
                added += 1
                LOG.debug("Added thumbnail file '%s' to submission '%s'", file_path, submission_id)

        if added:
            LOG.info("Added %d thumbnail file(s) to submission '%s'", added, submission_id)

    @override
    def registration_title(self, submission: Submission, rems: Rems) -> str:
        # The REMS catalogue item title format is:
        # <dataset short name> (<REMS organisation id>, <dataset id>).
        # The dataset short name, and dataset id are available from submission
        # name and id, respectively.
        return f"{submission.name} ({rems.organizationId}, {submission.submissionId})"

    @override
    def discovery_id(self, submission: Submission, registration: Registration) -> str:
        # Use the dataset id.
        return submission.submissionId

    @override
    def rems_resource_id(self, submission: Submission, registration: Registration) -> str:
        # Use the dataset id.
        return submission.submissionId

    @override
    async def is_published_to_rems(self, services: RESTAPIServices, submission: Submission) -> bool:
        # A non-clinical Bigpicture dataset is not published to REMS.
        policies = [xml async for xml in services.object.get_documents(submission.submissionId, BP_POLICY_OBJECT_TYPE)]
        if not policies:
            return True

        return is_clinical_policy(XmlObjectProcessor(self.xml_config(submission), policies[0]))


_PROFILES: dict[SubmissionWorkflow, SubmissionWorkflowProfile] = {
    profile.workflow: profile
    for profile in (SDSubmissionWorkflow(), FegaSubmissionWorkflow(), BigpictureSubmissionWorkflow())
}


def workflow_profile(workflow: SubmissionWorkflow) -> SubmissionWorkflowProfile:
    """
    Get the profile of a submission workflow.

    :param workflow: The submission workflow.
    :returns: The workflow profile.
    """
    return _PROFILES[workflow]
