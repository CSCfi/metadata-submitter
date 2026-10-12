"""Models of the sync API."""

from datetime import datetime

from pydantic import RootModel

from .base import StrictBaseModel


class SyncSubmission(StrictBaseModel):
    """A published submission for the sync client."""

    submissionId: str
    published: datetime
    ingested: datetime | None = None


class SyncSubmissions(StrictBaseModel):
    """Published submissions for the sync client, most recently published last."""

    submissions: list[SyncSubmission]


class SyncFile(StrictBaseModel):
    """A file associated with a published submission."""

    fileId: str
    objectId: str | None = None
    path: str


class SyncFiles(RootModel[list[SyncFile]]):
    """The files associated with a published submission."""
