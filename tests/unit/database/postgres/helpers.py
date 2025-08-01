import hashlib
import os
import uuid
from datetime import datetime
from typing import Any

from metadata_backend.api.models import File, ChecksumType, SubmissionWorkflow
from metadata_backend.database.postgres.models import SubmissionEntity, ObjectEntity


# Create entities used in Postgres repositories.
#

def create_submission_entity(
        *,
        name: str | None = None,
        project_id: str | None = None,
        folder: str | None = None,
        workflow: SubmissionWorkflow | None = SubmissionWorkflow.SDS,
        document: dict[str, Any] | None = None,
        is_published: bool = False,
        is_ingested: bool = False,
        created: datetime | None = None,
        modified: datetime | None = None
) -> SubmissionEntity:
    if name is None:
        name = f"name_{uuid.uuid4()}"
    if project_id is None:
        project_id = f"project_{uuid.uuid4()}"
    if folder is None:
        folder = f"folder_{uuid.uuid4()}"

    if not document:
        document = {}
    document = {
        "projectId": project_id,
        "name": name,
        "description": f"description_{uuid.uuid4()}",
        "workflow": workflow.value,
        **document
    }

    return SubmissionEntity(
        name=name,
        project_id=project_id,
        folder=folder,
        workflow=workflow,
        is_published=is_published,
        is_ingested=is_ingested,
        document=document,
        created=created,
        modified=modified,
    )


def create_object_entity(
        submission_id: str,
        *,
        name: str | None = None,
        schema: str | None = None,
        title: str | None = None,
        document: dict[str, Any] | None = None,
        xml_document: str | None = None,
        is_draft: bool = False
) -> ObjectEntity:
    if name is None:
        name = f"name_{uuid.uuid4()}"
    if schema is None:
        schema = f"type_{uuid.uuid4()}"
    if title is None:
        title = f"title_{uuid.uuid4()}"
    if document is None:
        document = {"test": "test"}
    if xml_document is None:
        xml_document = "<test/>"

    return ObjectEntity(
        submission_id=submission_id,
        name=name,
        schema=schema,
        title=title,
        document=document,
        xml_document=xml_document,
        is_draft=is_draft,
    )


# Create models used in Postgres services.
#

def create_file(
        submission_id: str,
        object_id: str,
        *,
        path: str | None = None,
        bytes: int = 1,
        unencrypted_checksum: str | None = None,
        unencrypted_checksum_type: ChecksumType | None = ChecksumType.MD5,
        encrypted_checksum: str | None = None,
        encrypted_checksum_type: ChecksumType | None = ChecksumType.MD5,
) -> File:
    if path is None:
        path = f"file{uuid.uuid4()}"
    if unencrypted_checksum is None:
        unencrypted_checksum = hashlib.md5(os.urandom(32)).hexdigest()
    if encrypted_checksum is None:
        encrypted_checksum = hashlib.md5(os.urandom(32)).hexdigest()

    return File(
        submission_id=submission_id,
        object_id=object_id,
        path=path,
        bytes=bytes,
        unencrypted_checksum=unencrypted_checksum,
        unencrypted_checksum_type=unencrypted_checksum_type,
        encrypted_checksum=encrypted_checksum,
        encrypted_checksum_type=encrypted_checksum_type,
    )
