"""Bigpicture API services."""

import io
import zipfile
from collections import defaultdict
from typing import Literal, override

import httpx
from pydantic import BaseModel

from ...database.postgres.services.file import FileService
from ...database.postgres.services.object import ObjectService
from ...helpers.logger import LOG
from ..exceptions import SystemException
from ..handlers.restapi import RESTAPIServices
from ..models.models import File
from ..models.submission import Submission, SubmissionWorkflow
from ..models.sync import SyncFile, SyncFiles
from ..processors.exceptions import InvalidDocumentException
from ..processors.xml.bigpicture import (
    BP_ANNOTATION_OBJECT_TYPE,
    BP_ANNOTATION_TASK_OBJECT_TYPE,
    BP_ANNOTATOR_OBJECT_TYPE,
    BP_DATASET_OBJECT_TYPE,
    BP_IMAGE_OBJECT_TYPE,
    BP_LANDING_PAGE_OBJECT_TYPE,
    BP_OBSERVATION_OBJECT_TYPE,
    BP_OBSERVER_OBJECT_TYPE,
    BP_ONTOLOGY_OBJECT_TYPE,
    BP_POLICY_OBJECT_TYPE,
    BP_SAMPLE_OBJECT_TYPES,
    BP_STAINING_OBJECT_TYPE,
    as_xml_set_document,
    get_xml_object_type_schema,
    update_landing_page_xml,
)
from ..processors.xml.datacite import DATACITE_OBJECT_TYPE, DATACITE_SCHEMA, DATACITE_XML_SCHEMA_DIR
from ..processors.xml.processors import XmlProcessor
from .file import S3InboxSDAService
from .submission.bigpicture_version import get_bp_xml_object_config
from .sync import SyncMetadataProvider


class XmlOutputFile(BaseModel):
    """XML output file name and object types."""

    name: str
    object_types: list[str]
    # If True then the XML file must have at least one object.
    # If False then the XML file will be written only if at least one object exists.
    mandatory: bool = True


class XmlOutputDir(BaseModel):
    """XML output directory and XML files."""

    dir: Literal["METADATA", "LANDING_PAGE", "PRIVATE"]
    files: list[XmlOutputFile]

    def get_full_dir(self, submission_id: str) -> str:
        """Get the full XML file directory including the dataset directory name.

        :param submission_id: the submission (dataset) id.
        :returns: the full XML file directory including the dataset directory name.
        """
        return f"DATASET_{submission_id}/{self.dir}"


# XML output files written to the METADATA, LANDING_PAGE and PRIVATE directories.
XML_OUTPUT_FILES: list[XmlOutputDir] = [
    XmlOutputDir(
        dir="METADATA",
        files=[
            XmlOutputFile(name="dataset.xml.c4gh", object_types=[BP_DATASET_OBJECT_TYPE]),
            XmlOutputFile(name="policy.xml.c4gh", object_types=[BP_POLICY_OBJECT_TYPE]),
            XmlOutputFile(name="image.xml.c4gh", object_types=[BP_IMAGE_OBJECT_TYPE]),
            XmlOutputFile(name="annotation.xml.c4gh", object_types=[BP_ANNOTATION_OBJECT_TYPE]),
            XmlOutputFile(name="observation.xml.c4gh", object_types=[BP_OBSERVATION_OBJECT_TYPE]),
            XmlOutputFile(name="observer.xml.c4gh", object_types=[BP_OBSERVER_OBJECT_TYPE]),
            XmlOutputFile(name="sample.xml.c4gh", object_types=BP_SAMPLE_OBJECT_TYPES),
            XmlOutputFile(name="staining.xml.c4gh", object_types=[BP_STAINING_OBJECT_TYPE]),
            # Since 3.0.
            XmlOutputFile(name="annotator.xml.c4gh", object_types=[BP_ANNOTATOR_OBJECT_TYPE], mandatory=False),
            XmlOutputFile(name="ontology.xml.c4gh", object_types=[BP_ONTOLOGY_OBJECT_TYPE], mandatory=False),
            XmlOutputFile(
                name="annotation_task.xml.c4gh", object_types=[BP_ANNOTATION_TASK_OBJECT_TYPE], mandatory=False
            ),
        ],
    ),
    XmlOutputDir(
        dir="LANDING_PAGE",
        files=[
            XmlOutputFile(name="landing_page.xml.c4gh", object_types=[BP_LANDING_PAGE_OBJECT_TYPE]),
        ],
    ),
]


def read_bp_public_key(response: httpx.Response) -> str:
    """
    Read the public key from the SDA login service's /info endpoint.

    :param response: The response of the login service.
    :return: The base64 encoded PEM public key.
    """

    public_key: str = response.json()["public_key"]
    return public_key


async def upload_bp_metadata_xmls(services: RESTAPIServices, submission_id: str, user_id: str, jwt: str) -> None:
    """Upload encrypted Bigpicture metadata XML files to SDA inbox.

    :param services: REST API services.
    :param submission_id: Submission ID.
    :param user_id: User ID.
    :param jwt: User JWT token.
    """
    file_provider = services.file_provider
    if not isinstance(file_provider, S3InboxSDAService):
        reason = "Bigpicture metadata upload requires SDA inbox file provider service."
        LOG.error(reason)
        raise SystemException(reason)

    bucket = user_id.replace("@", "_")  # SDA inbox bucket name is the user id with @ replaced by underscore
    registration = await services.registration.get_registration(submission_id)  # For landing page XML update
    config = get_bp_xml_object_config(await services.submission.get_submission_by_id(submission_id))

    for xml_output_dir in XML_OUTPUT_FILES:
        for file in xml_output_dir.files:
            # Get all XML documents for the schema type of the file.
            xml_docs = [
                xml_doc async for xml_doc in services.object.get_documents(submission_id, tuple(file.object_types))
            ]
            if not xml_docs:
                if file.mandatory:
                    reason = f"No XML objects found for: {file.name}"
                    LOG.error(reason)
                    raise SystemException(reason)
                continue

            # For landing page XML, update the REMS and DOI URL value from the registration.
            if BP_LANDING_PAGE_OBJECT_TYPE in file.object_types:
                try:
                    xml_docs = [
                        await update_landing_page_xml(
                            xml_doc,
                            config,
                            datacite_url=registration.dataciteUrl if registration else None,
                            rems_url=registration.remsUrl if registration else None,
                        )
                        for xml_doc in xml_docs
                    ]
                except InvalidDocumentException as ex:
                    reason = f"Stored XML document is not valid for {file.name}"
                    LOG.error(f"{reason}: {ex}")
                    raise SystemException(reason) from ex

            # Compile and validate the XML document.
            if DATACITE_OBJECT_TYPE in file.object_types:
                # DataCite XML is a single standalone namespaced document and is handled differently.
                if len(xml_docs) != 1:
                    reason = f"Expected exactly one DataCite XML document but found {len(xml_docs)}"
                    LOG.error(reason)
                    raise SystemException(reason)
                xml = xml_docs[0]
                try:
                    parsed_xml = XmlProcessor.parse_xml(xml)
                    XmlProcessor.validate_schema(parsed_xml, str(DATACITE_XML_SCHEMA_DIR), "metadata.xsd")
                except Exception as ex:
                    reason = f"Generated XML document is not valid for {file.name}"
                    LOG.error(f"reason: {str(ex)}")
                    raise SystemException(reason)
            else:
                # BP XML types are wrapped in a set element and validated against the schemas
                # of the submission's version.
                schema_type = config.get_schema_type(file.object_types[0])
                xml = await as_xml_set_document(xml_docs, schema_type, config)
                try:
                    parsed_xml = XmlProcessor.parse_xml(xml)
                    XmlProcessor.validate_schema(
                        parsed_xml,
                        config.schema_dir,
                        schema_type,
                        config.schema_file_resolver,
                    )
                except Exception as ex:
                    reason = f"Generated XML document is not valid for {file.name}"
                    LOG.error(f"reason: {str(ex)}")
                    raise SystemException(reason)

            # Upload the XML document to SDA inbox.
            LOG.info(f"Uploading XML document for {file.name} in submission {submission_id} to SDA inbox.")
            prefix = xml_output_dir.get_full_dir(submission_id)
            object_key = f"{prefix}/{file.name}"
            xml_bytes = xml.encode("utf-8")
            await file_provider._add_file_to_bucket(
                bucket_name=bucket,
                object_key=object_key,
                access_key=bucket,
                secret_key=bucket,
                session_token=jwt,
                body=xml_bytes,
            )

            # Add uploaded XML artifacts to submission file records for ingestion workflow.
            if not await services.file.is_file_by_path(submission_id, object_key):
                await services.file.add_file(
                    File(submissionId=submission_id, path=object_key),
                    SubmissionWorkflow.BP,
                )


BP_SYNC_METADATA_DIR = "METADATA"
BP_SYNC_FILES_PATH = "FILES/files.json"


class BigpictureSyncMetadataProvider(SyncMetadataProvider):
    """Package the metadata objects of a Bigpicture submission for sync."""

    def __init__(self, object_service: ObjectService, file_service: FileService) -> None:
        """
        Package the metadata objects of a Bigpicture submission for sync.

        :param object_service: The object service used to read the metadata objects.
        :param file_service: The file service used to read the files.
        """
        self._object_service = object_service
        self._file_service = file_service

    @override
    async def get_metadata_archive(self, submission: Submission) -> bytes:
        """
        Get the metadata objects of one submission as a zip archive.

        One document per schema, holding every metadata object of that schema. DataCite
        is handled separately. The files of the submission, with their accessions, are
        listed in a JSON document.

        :param submission: The submission.
        :return: The zip archive of the metadata objects.
        """

        submission_id = submission.submissionId
        objects = await self._object_service.get_objects(submission_id)
        config = get_bp_xml_object_config(submission)

        object_types_by_schema: dict[str, list[str]] = defaultdict(list)
        for obj in objects:
            # The DataCite object type is not one of the Bigpicture schemas.
            schema_type = (
                DATACITE_SCHEMA
                if obj.objectType == DATACITE_OBJECT_TYPE
                else get_xml_object_type_schema(obj.objectType)
            )
            if obj.objectType not in object_types_by_schema[schema_type]:
                object_types_by_schema[schema_type].append(obj.objectType)

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for schema_type, object_types in sorted(object_types_by_schema.items()):
                xml_documents = [
                    xml_document
                    async for xml_document in self._object_service.get_documents(submission_id, object_types)
                ]
                if not xml_documents:
                    continue

                if schema_type == DATACITE_SCHEMA:
                    if len(xml_documents) != 1:
                        reason = f"Expected exactly one DataCite XML document but found {len(xml_documents)}"
                        LOG.error(reason)
                        raise SystemException(reason)
                    document = xml_documents[0]
                else:
                    document = await as_xml_set_document(xml_documents, schema_type, config)

                archive.writestr(f"{BP_SYNC_METADATA_DIR}/{schema_type}.xml", document)

            archive.writestr(
                BP_SYNC_FILES_PATH, (await self._get_files(submission_id)).model_dump_json(indent=2, exclude_none=True)
            )

        return buffer.getvalue()

    async def _get_files(self, submission_id: str) -> SyncFiles:
        """
        Get the files of one submission, ordered by path.

        :param submission_id: The submission id.
        :return: The files of the submission.
        """

        files = [
            SyncFile(
                fileId=file.fileId,
                objectId=file.objectId,
                path=file.path,
            )
            async for file in self._file_service.get_files(submission_id=submission_id)
            if file.fileId is not None
        ]
        return SyncFiles(root=sorted(files, key=lambda file: file.path))
