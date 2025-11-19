"""Other models."""

from datetime import datetime
from typing import Literal, Optional

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


class Project(StrictBaseModel):
    """A user project."""

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


class Objects(StrictBaseModel):
    """List of metadata objects."""

    objects: list[Object]


class File(StrictBaseModel):
    """A file associated with the submission."""

    fileId: Optional[str] = None
    submissionId: Optional[str] = None
    objectId: Optional[str] = None
    path: str
    bytes: Optional[int] = None
    checksumMethod: Optional[ChecksumMethodType] = None
    unencryptedChecksum: Optional[str] = None
    encryptedChecksum: Optional[str] = None


class Files(RootModel[list[File]]):
    """List of files."""


class Registration(StrictBaseModel):
    """A registration entry to an external service."""

    submissionId: str = None
    objectId: Optional[str] = None
    objectType: Optional[str] = None
    title: str
    description: str
    doi: str
    metaxId: Optional[str] = None
    dataciteUrl: Optional[str] = None
    remsUrl: Optional[str] = None
    remsResourceId: Optional[str] = None
    remsCatalogueId: Optional[str] = None
