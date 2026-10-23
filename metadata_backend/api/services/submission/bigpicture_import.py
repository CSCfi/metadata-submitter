"""Service for importing Bigpicture datasets that were accessioned and archived outside SD Submit."""

from typing import Iterable, Sequence, override

from ....conf.deployment import deployment_config
from ....database.postgres.services.file import FileService
from ....database.postgres.services.object import ObjectService
from ....database.postgres.services.submission import SubmissionService
from ....helpers.logger import LOG
from ....services.admin_service import AdminServiceHandler
from ....services.rems_service import RemsServiceHandler
from ...exceptions import UserException, UserExceptions
from ...models.models import File, IngestStatus
from ...models.sda import DatasetFile, DatasetStatus
from ...models.submission import Rems, Submission
from ...processors.models import ObjectIdentifier
from ...processors.xml.bigpicture import BP_DATASET_OBJECT_TYPE, BP_DATASET_SCHEMA, BP_LANDING_PAGE_OBJECT_TYPE
from ...processors.xml.processors import XmlStringDocumentsProcessor
from ..accession import generate_bp_accession_prefix, is_bp_accession
from ..bigpicture import BP_METADATA_FILE_PATHS, get_bp_ingested_dataset_root, get_bp_metadata_file_paths
from ..project import ProjectService
from ..rems import find_rems_catalogue_item, find_rems_resource
from .bigpicture import BigpictureObjectSubmissionService
from .bigpicture_policy import is_clinical_policy, policy_processor
from .submission import ObjectSubmission

# mypy: disable_error_code = misc


def _relative_path(root: str, path: str) -> str:
    """
    Get the path of a file below a root directory, without the encryption suffix.

    :param root: The root directory.
    :param path: The file path.
    :returns: The relative path.
    """
    return path.removeprefix(f"{root}/").removesuffix(".c4gh")


class BigpictureObjectImportService(BigpictureObjectSubmissionService):
    """
    Service for importing Bigpicture datasets that were accessioned and archived outside SD Submit.

    The metadata objects are validated as for a new submission. Only the dataset may have an
    accession, which is kept and used as the submission id. The dataset must exist in SDA, its files
    must share one root directory, and below it they must be laid out as for a new submission: the
    data files in the metadata, the thumbnails and the metadata XMLs. The data files and thumbnails
    are saved with their SDA paths and accessions, as already ingested. The root directory replaces
    DATASET_{submission id} for this submission, so the newly accessioned metadata XMLs are written to
    the paths of the old ones, which they replace in SDA after the submission is published.
    """

    def __init__(
        self,
        project_service: ProjectService,
        submission_service: SubmissionService,
        object_service: ObjectService,
        file_service: FileService,
        admin_handler: AdminServiceHandler,
        rems_handler: RemsServiceHandler,
    ) -> None:
        """
        Service for importing Bigpicture datasets.

        :param project_service: The Postgres project service.
        :param submission_service: The Postgres submission service.
        :param object_service: The Postgres object service.
        :param file_service: The Postgres file service.
        :param admin_handler: The SDA Admin API service handler.
        :param rems_handler: The REMS service handler.
        """
        super().__init__(project_service, submission_service, object_service, file_service)
        self._admin_handler = admin_handler
        self._rems_handler = rems_handler

    @override
    def create_processor(self, objects: list[ObjectSubmission]) -> XmlStringDocumentsProcessor | None:
        processor = super().create_processor(objects)
        if self._datacite_xml is not None:
            raise UserException("DataCite XML is not supported when importing a dataset.")
        return processor

    def _dataset_id(self) -> str | None:
        """
        Get the dataset accession given in the dataset metadata object.

        :returns: The dataset accession.
        """
        # The BP XML processor guarantees that we have one dataset metadata object.
        return self._processor.get_object_identifiers(BP_DATASET_SCHEMA)[0].id

    @override
    def check_submitted_object_accessions(self, identifiers: Sequence[ObjectIdentifier]) -> list[str]:
        errors = []
        for identifier in identifiers:
            if identifier.object_type == BP_DATASET_OBJECT_TYPE:
                if identifier.id is None:
                    errors.append(f"The imported '{identifier.schema_type}' metadata object must have an accession")
                elif not is_bp_accession(identifier.id, identifier.object_type):
                    prefix = generate_bp_accession_prefix(identifier.object_type)
                    errors.append(
                        f"The imported '{identifier.schema_type}' metadata object accession '{identifier.id}' "
                        f"is not a Bigpicture accession with the prefix '{prefix}'"
                    )
            elif identifier.id is not None:
                errors.append(
                    f"The imported '{identifier.schema_type}' metadata object must not have an accession: "
                    f"'{identifier.id}'"
                )
        return errors

    @override
    def check_submitted_reference_accessions(self, references: Sequence[ObjectIdentifier]) -> list[str]:
        dataset_id = self._dataset_id()
        return [
            f"The imported reference to '{identifier.schema_type}' metadata object must not have an accession: "
            f"'{identifier.id}'"
            for identifier in references
            if identifier.id is not None and identifier.id != dataset_id
        ]

    @override
    async def create(self, user_id: str, project_id: str, objects: list[ObjectSubmission]) -> Submission:
        submission = await super().create(user_id, project_id, objects)
        submission_id = submission.submissionId
        await self._submission_service.update_imported(submission_id)
        LOG.info("Imported dataset '%s'.", submission_id)
        # Get the submission from database because imported and dateImported have been updated.
        return await self._submission_service.get_submission_by_id(submission_id)

    @override
    async def update(
        self, user_id: str, project_id: str, submission_id: str, objects: list[ObjectSubmission]
    ) -> Submission:
        raise UserException(f"Imported submission '{submission_id}' cannot be updated. Delete it and import it again.")

    @override
    async def _add_file(self, file: File) -> None:
        # A file with an id is already archived in SDA.
        ingest_status = IngestStatus.READY if file.fileId is not None else None
        await self._file_service.add_file(file, self._workflow, ingest_status=ingest_status)

    @override
    async def resolve_files(self, submission: Submission, files: list[File]) -> list[File]:
        """
        Check the imported dataset against SDA, and return its files with their SDA paths and accessions.

        The import is rejected if:
        - a submission with the dataset accession already exists
        - the dataset does not exist in SDA, is deprecated, or has no files
        - the dataset files in SDA are not under one root directory
        - the dataset's existing REMS resource or catalogue item has another organisation or workflow
        - the metadata XMLs in SDA are not the ones the import will write (a landing page may be added)
        - a data file in the metadata is not in SDA at the same path below the root directory
        - SDA has a file that is not a metadata XML, a data file in the metadata, or a thumbnail

        The errors found in the dataset files are all reported together.

        The data files in the metadata, and the thumbnails, are returned with their SDA accession as the file
        id and their SDA path. The old metadata XMLs are not returned, the new ones
        replace them in SDA after the submission is published.

        :param submission: The prepared submission document, whose id is the dataset accession.
        :param files: The data files in the metadata, under the default root directory.
        :returns: The data files and thumbnails, with their SDA paths and accessions.
        """
        submission_id = submission.submissionId

        # Two concurrent imports of the same dataset can both pass the 'has already been submitted'
        # check below. Both will later call SubmissionService.add_submission to insert the
        # submission in the database. The second insert will violate the primary key
        # of the submissions table, and the database raises an IntegrityError, which is returned as an
        # unexpected 500 error rather than the UserException below. This is accepted, because no external
        # service state is changed before the insert.
        if await self._submission_service.is_submission_by_id(submission_id):
            raise UserException(f"Dataset '{submission_id}' has already been submitted.")

        dataset_status = await self._admin_handler.get_dataset_status(submission_id)
        if dataset_status == DatasetStatus.DEPRECATED:
            raise UserException(f"Dataset '{submission_id}' has been deprecated in SDA.")

        sda_files = await self._admin_handler.list_ingested_files(submission_id)
        if sda_files is None:
            raise UserException(f"Dataset '{submission_id}' does not exist in SDA.")
        if not sda_files:
            raise UserException(f"Dataset '{submission_id}' has no files in SDA.")

        root = get_bp_ingested_dataset_root(file.path for file in sda_files)
        if root is None:
            raise UserException(f"Dataset '{submission_id}' files in SDA are not under one root directory.")

        await self._check_rems(submission_id, submission.rems)

        errors: list[str] = []
        sda_file_by_path: dict[str, DatasetFile] = {}
        for sda_file in sda_files:
            path = _relative_path(root, sda_file.path)
            # The import matches each data file in the metadata to the one SDA file at its path, and saves that
            # file's accession. SDA allows two files with the same path in a dataset, for example a file ingested
            # twice, or the same path with and without .c4gh. Then the import cannot tell which accession to
            # save, and the other file would be left in the dataset unknown to SD Submit. So it is rejected.
            if path in sda_file_by_path:
                errors.append(f"Dataset '{submission_id}' has more than one file '{path}' in SDA.")
            sda_file_by_path[path] = sda_file

        # The metadata XMLs in SDA must be the same ones that are being imported, so that each imported XML
        # replaces an old one. The exception is the landing page XML, which may be added if SDA has none.
        errors.extend(self._check_metadata_files(submission_id, sda_file_by_path.keys()))

        # Find each data file in the metadata in SDA, at the same path below the root directory. A found file
        # gets its SDA accession as its file id and its SDA path, and is removed from the SDA files left to
        # check. A file not in SDA is an error.
        matched_sda_files: list[File] = []
        # Data files references by metadata.
        for file in files:
            # The path below the root directory.
            _, _, path = file.path.partition("/")
            path = path.removesuffix(".c4gh")
            sda_file = sda_file_by_path.pop(path, None)
            if sda_file is None:
                errors.append(f"Dataset '{submission_id}' has no file '{path}' in SDA.")
                continue
            matched_sda_files.append(file.model_copy(update={"fileId": sda_file.accession_id, "path": sda_file.path}))

        # Thumbnails, not referenced by metadata. Any other file is unexpected.
        thumbnails: list[File] = []
        for path, sda_file in sda_file_by_path.items():
            if path in BP_METADATA_FILE_PATHS:
                continue
            if path.startswith("LANDING_PAGE/THUMBNAILS/") and path.lower().endswith(".jpg"):
                thumbnails.append(
                    File(
                        submissionId=submission_id,
                        fileId=sda_file.accession_id,
                        path=sda_file.path,
                    )
                )
            else:
                errors.append(f"Dataset '{submission_id}' has file '{path}' in SDA, which is not imported.")

        if not errors and not matched_sda_files and not thumbnails:
            errors.append(f"Dataset '{submission_id}' has no data files in SDA.")
        if errors:
            raise UserExceptions(errors)

        LOG.info(
            "Dataset '%s' has %d data file(s) and %d thumbnail(s) under '%s' in SDA.",
            submission_id,
            len(matched_sda_files),
            len(thumbnails),
            root,
        )
        return matched_sda_files + thumbnails

    async def _check_rems(self, submission_id: str, rems: Rems) -> None:
        """
        Check that publishing can reuse the REMS resource and catalogue item of the dataset, if it has them.

        :param submission_id: The submission id, which is the dataset accession and REMS resource id.
        :param rems: The REMS metadata of the submission.
        :raises UserException: If the REMS resource or catalogue item has another organization or workflow.
        """
        if not deployment_config().ALLOW_REGISTRATION:
            return
        if not is_clinical_policy(policy_processor(self._processor)):
            # A non-clinical dataset is not published to REMS.
            return

        # Validate the REMS workflow defined in rems.xml, so that an invalid one fails during import
        # and not during publish.
        rems_workflow = await self._rems_handler.get_workflow(rems.organizationId, rems.workflowId)
        organization_id = rems_workflow.organization.id
        resource = await find_rems_resource(self._rems_handler, submission_id, organization_id)
        if resource is not None:
            LOG.info("Dataset '%s' already has a REMS resource, which publishing will reuse.", submission_id)
        # Without an active resource, publishing creates one, so an active catalogue item is an error.
        await find_rems_catalogue_item(
            self._rems_handler,
            submission_id,
            organization_id,
            rems.workflowId,
            resource.id if resource is not None else None,
        )

    def _check_metadata_files(self, submission_id: str, sda_paths: Iterable[str]) -> list[str]:
        """
        Check that the metadata XMLs in SDA are the ones that publishing will replace.

        A landing page may be added, if the SDA dataset does not have one.

        :param submission_id: The submission id.
        :param sda_paths: The paths of the dataset files in SDA, below the root directory.
        :returns: The errors.
        """

        # Object types found in the imported XMLs.
        object_types = {identifier.object_type for identifier in self._processor.get_object_identifiers()}
        imported_xml_paths = get_bp_metadata_file_paths(object_types)
        landing_page_xml_paths = get_bp_metadata_file_paths([BP_LANDING_PAGE_OBJECT_TYPE])
        sda_xml_paths = set(sda_paths) & BP_METADATA_FILE_PATHS

        errors = [
            f"Dataset '{submission_id}' has metadata file '{path}' in SDA, which is not imported."
            for path in sorted(sda_xml_paths - imported_xml_paths)
        ]
        errors.extend(
            f"Dataset '{submission_id}' has no metadata file '{path}' in SDA."
            for path in sorted(imported_xml_paths - sda_xml_paths - landing_page_xml_paths)
        )
        return errors
