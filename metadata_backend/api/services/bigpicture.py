"""Bigpicture API services."""

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
    as_xml_set_document,
    update_landing_page_xml,
)
from .file import S3InboxSDAService

BP_METADATA_FILES: tuple[tuple[str | tuple[str, ...], str], ...] = (
    (BP_DATASET_OBJECT_TYPE, "dataset.xml.c4gh"),
    (BP_POLICY_OBJECT_TYPE, "policy.xml.c4gh"),
    (BP_IMAGE_OBJECT_TYPE, "image.xml.c4gh"),
    (BP_ANNOTATION_OBJECT_TYPE, "annotation.xml.c4gh"),
    (BP_OBSERVATION_OBJECT_TYPE, "observation.xml.c4gh"),
    (BP_OBSERVER_OBJECT_TYPE, "observer.xml.c4gh"),
    (tuple(BP_SAMPLE_OBJECT_TYPES), "sample.xml.c4gh"),
    (BP_STAINING_OBJECT_TYPE, "staining.xml.c4gh"),
)

BP_LANDING_PAGE: tuple[tuple[str, str], ...] = ((BP_LANDING_PAGE_OBJECT_TYPE, "landing_page.xml.c4gh"),)

BP_PRIVATE_METADATA_FILES: tuple[tuple[str, str], ...] = (
    (BP_ORGANISATION_OBJECT_TYPE, "organisation.xml.c4gh"),
    (BP_REMS_OBJECT_TYPE, "rems.xml.c4gh"),
)


async def upload_bp_metadata_xmls(services: RESTAPIServices, submission_id: str, user_id: str, jwt: str) -> None:
    """Upload encrypted Bigpicture metadata XML files to SDA inbox.

    :param services: REST API services.
    :param submission_id: Submission ID.
    :param user_id: User ID.
    :param jwt: User JWT token.
    """
    file_provider = services.file_provider
    if not isinstance(file_provider, S3InboxSDAService):
        raise SystemException("Bigpicture metadata upload requires SDA inbox file provider service.")

    bucket = user_id.replace("@", "_")  # SDA inbox bucket name is the user id with @ replaced by underscore
    registration = await services.registration.get_registration(submission_id)  # For landing page XML update

    file_prefixes = (
        (BP_METADATA_FILES, f"DATASET_{submission_id}/METADATA"),  # Metadata XML files
        (BP_LANDING_PAGE, f"DATASET_{submission_id}/LANDING_PAGE"),  # Landing page XML file
        (BP_PRIVATE_METADATA_FILES, f"DATASET_{submission_id}/PRIVATE"),  # Private metadata XML files
    )

    for object_files, prefix in file_prefixes:
        for object_type, filename in object_files:
            xml_docs = [xml_doc async for xml_doc in services.object.get_xml_documents(submission_id, object_type)]
            if not xml_docs:
                continue

            # For landing page XML, update the REMS and DOI URL value from the registration.
            if object_type == BP_LANDING_PAGE_OBJECT_TYPE:
                xml_docs = [
                    await update_landing_page_xml(
                        xml_doc,
                        datacite_url=registration.dataciteUrl if registration else None,
                        rems_url=registration.remsUrl if registration else None,
                    )
                    for xml_doc in xml_docs
                ]

            xml = await as_xml_set_document(xml_docs, object_type)
            object_key = f"{prefix}/{filename}"
            await file_provider._add_file_to_bucket(
                bucket_name=bucket,
                object_key=object_key,
                access_key=user_id,
                secret_key=user_id,
                session_token=jwt,
                body=xml.encode("utf-8"),
            )
