"""Bigpicture API services."""

from typing import Literal

from pydantic import BaseModel

from ...helpers.logger import LOG
from ..exceptions import SystemException
from ..handlers.restapi import RESTAPIServices
from ..processors.xml.bigpicture import (
    BP_ANNOTATION_OBJECT_TYPE,
    BP_DATASET_OBJECT_TYPE,
    BP_IMAGE_OBJECT_TYPE,
    BP_LANDING_PAGE_OBJECT_TYPE,
    BP_OBSERVATION_OBJECT_TYPE,
    BP_OBSERVER_OBJECT_TYPE,
    BP_ORGANISATION_OBJECT_TYPE,
    BP_POLICY_OBJECT_TYPE,
    BP_REMS_OBJECT_TYPE,
    BP_SAMPLE_OBJECT_TYPES,
    BP_STAINING_OBJECT_TYPE,
    BP_XML_OBJECT_CONFIG,
    as_xml_set_document,
    update_landing_page_xml,
)
from ..processors.xml.processors import XmlProcessor
from .file import S3InboxSDAService


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
        ],
    ),
    XmlOutputDir(
        dir="LANDING_PAGE",
        files=[
            XmlOutputFile(name="landing_page.xml.c4gh", object_types=[BP_LANDING_PAGE_OBJECT_TYPE]),
        ],
    ),
    XmlOutputDir(
        dir="PRIVATE",
        files=[
            XmlOutputFile(name="organisation.xml.c4gh", object_types=[BP_ORGANISATION_OBJECT_TYPE]),
            XmlOutputFile(name="rems.xml.c4gh", object_types=[BP_REMS_OBJECT_TYPE]),
            # TODO(improve): Add datacite XML file when datacite XML metadata is available
            # XmlOutputFile(name="datacite.xml.c4gh", object_types=[DATACITE_OBJECT_TYPE]),
        ],
    ),
]


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

    for xml_output_dir in XML_OUTPUT_FILES:
        for file in xml_output_dir.files:
            # Get all XML documents for the schema type of the file.
            xml_docs = [
                xml_doc async for xml_doc in services.object.get_xml_documents(submission_id, tuple(file.object_types))
            ]
            if not xml_docs:
                if file.mandatory:
                    reason = f"No XML objects found for: {file.name}"
                    LOG.error(reason)
                    raise SystemException(reason)
                continue

            # For landing page XML, update the REMS and DOI URL value from the registration.
            if BP_LANDING_PAGE_OBJECT_TYPE in file.object_types:
                xml_docs = [
                    await update_landing_page_xml(
                        xml_doc,
                        datacite_url=registration.dataciteUrl if registration else None,
                        rems_url=registration.remsUrl if registration else None,
                    )
                    for xml_doc in xml_docs
                ]

            # Compile the XML documents into a single XML document.
            schema_type = BP_XML_OBJECT_CONFIG.get_schema_type(file.object_types[0])
            xml = await as_xml_set_document(xml_docs, schema_type)

            # Validate the new XML document
            try:
                parsed_xml = XmlProcessor.parse_xml(xml)
                XmlProcessor.validate_schema(
                    parsed_xml,
                    BP_XML_OBJECT_CONFIG.schema_dir,
                    schema_type,
                    BP_XML_OBJECT_CONFIG.schema_file_resolver,
                )
            except Exception as ex:
                reason = f"Generated XML document is not valid for {file.name}"
                LOG.error(f"reason: {str(ex)}")
                raise SystemException(reason)

            # Upload the XML document to SDA inbox.
            LOG.info(f"Uploading XML document for {file.name} in submission {submission_id} to SDA inbox.")
            prefix = xml_output_dir.get_full_dir(submission_id)
            object_key = f"{prefix}/{file.name}"
            await file_provider._add_file_to_bucket(
                bucket_name=bucket,
                object_key=object_key,
                access_key=user_id,
                secret_key=user_id,
                session_token=jwt,
                body=xml.encode("utf-8"),
            )
