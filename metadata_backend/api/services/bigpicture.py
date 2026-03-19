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

BP_PRIVATE_METDATA_FILES: tuple[tuple[str, str], ...] = (
    (BP_ORGANISATION_OBJECT_TYPE, "organisation.xml.c4gh"),
    (BP_REMS_OBJECT_TYPE, "rems.xml.c4gh"),
)


async def _upload_xml_documents(
    services: RESTAPIServices,
    file_provider: S3InboxSDAService,
    *,
    bucket_name: str,
    prefix: str,
    object_files: tuple[tuple[str | tuple[str, ...], str], ...],
    user_id: str,
    jwt: str,
    submission_id: str,
) -> None:
    for object_type, filename in object_files:
        xml = None
        async for xml_doc in services.object.get_xml_documents(submission_id, object_type):
            xml = xml_doc
            break
        if xml is None:
            continue

        object_key = f"{prefix}/{filename}"
        await file_provider._add_file_to_bucket(
            bucket_name=bucket_name,
            object_key=object_key,
            access_key=user_id,
            secret_key=user_id,
            session_token=jwt,
            body=xml.encode("utf-8"),
        )


async def upload_bp_metadata_xmls(services: RESTAPIServices, submission_id: str, user_id: str, jwt: str) -> None:
    """Upload encrypted Bigpicture metadata XML files to SDA inbox."""
    file_provider = services.file_provider
    if not isinstance(file_provider, S3InboxSDAService):
        raise SystemException("Bigpicture metadata upload requires SDA inbox file provider service.")

    bucket = user_id.replace("@", "_")  # SDA inbox bucket name is the user id with @ replaced by underscore

    # Metadata XML files
    await _upload_xml_documents(
        services,
        file_provider,
        bucket_name=bucket,
        prefix=f"DATASET_{submission_id}/METADATA",
        object_files=BP_METADATA_FILES,
        user_id=user_id,
        jwt=jwt,
        submission_id=submission_id,
    )

    # Landing page XML file
    await _upload_xml_documents(
        services,
        file_provider,
        bucket_name=bucket,
        prefix=f"DATASET_{submission_id}/LANDING_PAGE",
        object_files=BP_LANDING_PAGE,
        user_id=user_id,
        jwt=jwt,
        submission_id=submission_id,
    )

    # Private metadata XML files
    # TODO(improve): Add datacite.xml to private metadata files once datacite.xml is available
    await _upload_xml_documents(
        services,
        file_provider,
        bucket_name=bucket,
        prefix=f"DATASET_{submission_id}/PRIVATE",
        object_files=BP_PRIVATE_METDATA_FILES,
        user_id=user_id,
        jwt=jwt,
        submission_id=submission_id,
    )
