"""Models of the sync API."""

from datetime import datetime

from .base import StrictBaseModel


class SyncSubmission(StrictBaseModel):
    """A published submission for the sync client."""

    submissionId: str
    published: datetime


class SyncSubmissions(StrictBaseModel):
    """Published submissions for the sync client, most recently published last."""

    submissions: list[SyncSubmission]
