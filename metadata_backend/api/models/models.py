"""Other models."""

from datetime import datetime
from typing import Literal

from pydantic import RootModel

from .base import StrictBaseModel

ChecksumMethodType = Literal["MD5", "SHA256"]
CHECKSUM_METHOD_TYPES = ("MD5", "SHA256")


class ApiKey(StrictBaseModel):
    """An API key."""

    key_id: str
    created_at: datetime | None = None


class User(StrictBaseModel):
    """A user."""

    user_id: str
    user_name: str
    projects: list["Project"] = []


class SubmissionId(StrictBaseModel):
    """Submission id."""

    submissionId: str


class Project(StrictBaseModel):
    """Project."""

    project_id: str


class Object(StrictBaseModel):
    """A metadata object."""

    name: str
    objectId: str
    objectType: str
    submissionId: str
    title: str | None = None
    description: str | None = None
    created: datetime | None = None
    modified: datetime | None = None


class Objects(RootModel[list[Object]]):
    """List of objects."""


class File(StrictBaseModel):
    """A file associated with the submission."""

    fileId: str | None = None
    submissionId: str | None = None
    objectId: str | None = None
    path: str
    bytes: int | None = None
    checksumMethod: ChecksumMethodType | None = None
    unencryptedChecksum: str | None = None
    encryptedChecksum: str | None = None


class Files(RootModel[list[File]]):
    """List of files."""


class Registration(StrictBaseModel):
    """A registration entry to an external service."""

    submissionId: str | None = None
    objectId: str | None = None
    objectType: str | None = None
    title: str
    description: str
    doi: str | None = None
    metaxId: str | None = None
    dataciteUrl: str | None = None
    remsUrl: str | None = None
    remsResourceId: str | None = None
    remsCatalogueId: str | None = None
