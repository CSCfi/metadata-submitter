import hashlib
import os
import uuid
from datetime import datetime
from typing import Any

from metadata_backend.api.models.models import File
from metadata_backend.api.models.submission import SubmissionWorkflow
from metadata_backend.database.postgres.models import ObjectEntity, SubmissionEntity

# Create entities used in Postgres repositories.
#


def create_submission_entity(
    *,
    name: str | None = None,
    project_id: str | None = None,
    bucket: str | None = None,
    workflow: SubmissionWorkflow | None = SubmissionWorkflow.SD,
    title: str | None = None,
    description: str | None = None,
    document: dict[str, Any] | None = None,
    is_published: bool = False,
    is_ingested: bool = False,
    created: datetime | None = None,
    modified: datetime | None = None,
) -> SubmissionEntity:
    if name is None:
        name = f"name_{uuid.uuid4()}"
    if project_id is None:
        project_id = f"project_{uuid.uuid4()}"

    if title is None:
        title = f"title_{uuid.uuid4()}"
    if description is None:
        description = f"description_{uuid.uuid4()}"

    if not document:
        document = {}
    document = {
        "projectId": project_id,
        "name": name,
        "title": title,
        "description": description,
        "workflow": workflow.value,
        **document,
    }

    return SubmissionEntity(
        name=name,
        project_id=project_id,
        bucket=bucket,
        workflow=workflow,
        is_published=is_published,
        is_ingested=is_ingested,
        title=title,
        description=description,
        document=document,
        created=created,
        modified=modified,
    )


def create_object_entity(
    project_id: str,
    submission_id: str,
    *,
    name: str | None = None,
    object_type: str | None = None,
    title: str | None = None,
    description: str | None = None,
    document: dict[str, Any] | None = None,
    xml_document: str | None = None,
) -> ObjectEntity:
    if name is None:
        name = f"name_{uuid.uuid4()}"
    if object_type is None:
        object_type = f"type_{uuid.uuid4()}"
    if title is None:
        title = f"title_{uuid.uuid4()}"
    if description is None:
        description = f"description_{uuid.uuid4()}"
    if document is None:
        document = {"test": "test"}
    if xml_document is None:
        xml_document = "<test/>"

    return ObjectEntity(
        project_id=project_id,
        submission_id=submission_id,
        name=name,
        object_type=object_type,
        title=title,
        description=description,
        document=document,
        xml_document=xml_document,
    )


# Create models used in Postgres services.
#


def create_file(
    submission_id: str,
    object_id: str,
    *,
    path: str | None = None,
    bytes: int = 1,
    checksum_method: str | None = "MD5",
    unencrypted_checksum: str | None = None,
    encrypted_checksum: str | None = None,
) -> File:
    if path is None:
        path = f"file{uuid.uuid4()}"
    if unencrypted_checksum is None:
        unencrypted_checksum = hashlib.md5(os.urandom(32)).hexdigest()
    if encrypted_checksum is None:
        encrypted_checksum = hashlib.md5(os.urandom(32)).hexdigest()

    return File(
        submissionId=submission_id,
        objectId=object_id,
        path=path,
        bytes=bytes,
        checksumMethod=checksum_method,
        unencryptedChecksum=unencrypted_checksum,
        encryptedChecksum=encrypted_checksum,
    )
