"""Sync API handler.

The sync endpoints allow other services to retrieve all published metadata.
"""

from datetime import datetime
from typing import Annotated

from fastapi import Query
from starlette.responses import Response

from ..dependencies import SubmissionIdPathParam, WorkflowDependency
from ..exceptions import NotFoundUserException, SystemException, UserException
from ..models.sync import SyncSubmissions
from ..services.sync import SyncMetadataProvider
from .restapi import RESTAPIHandler, RESTAPIServiceHandlers, RESTAPIServices

PublishedStartQueryParam = Annotated[
    datetime | None,
    Query(
        alias="publishedStart",
        description=(
            "The first publication date to return, inclusive, with a UTC offset. Everything "
            "published up to the end date when it is not given."
        ),
    ),
]
PublishedEndQueryParam = Annotated[
    datetime | None,
    Query(
        alias="publishedEnd",
        description=(
            "The last publication date to return, inclusive, with a UTC offset. Everything "
            "published since the start date when it is not given."
        ),
    ),
]


def _validate_utc_offset(name: str, value: datetime | None) -> None:
    """Require a date to specify a UTC offset.

    Avoids the risk of dates without UTC offset being resolved in the
    timezone of the database.

    :param name: The query parameter name.
    :param value: The publication date, or None when it was not given.
    :raises UserException: if the publication date does not specify a UTC offset.
    """

    if value is not None and value.utcoffset() is None:
        raise UserException(f"The '{name}' date must specify a UTC offset.")


class SyncAPIHandler(RESTAPIHandler):
    """Sync API handler."""

    def __init__(
        self,
        services: RESTAPIServices,
        handlers: RESTAPIServiceHandlers,
        sync_provider: SyncMetadataProvider | None = None,
    ) -> None:
        """
        Sync API handler.

        :param services: The services.
        :param handlers: The service handlers.
        :param sync_provider: How the deployment packages the metadata objects of a
            submission, or None for a deployment that does not package them.
        """
        super().__init__(services, handlers)
        self._sync_provider = sync_provider

    async def list_published_submissions(
        self,
        workflow: WorkflowDependency,
        published_start: PublishedStartQueryParam = None,
        published_end: PublishedEndQueryParam = None,
    ) -> SyncSubmissions:
        """Get the submissions published within the given period, most recently published last."""

        _validate_utc_offset("publishedStart", published_start)
        _validate_utc_offset("publishedEnd", published_end)

        if published_start is not None and published_end is not None and published_end < published_start:
            raise UserException("The publication period ends before it starts.")

        # The deployment has one workflow, and only its own submissions are synced.
        submissions = await self._services.submission.get_published_submissions(
            published_start, published_end, workflow=workflow
        )
        return SyncSubmissions(submissions=submissions)

    async def get_submission_metadata(self, submission_id: SubmissionIdPathParam) -> Response:
        """Get the metadata objects of one published submission as a zip archive."""

        if self._sync_provider is None:
            raise SystemException("The deployment does not package metadata objects for syncing.")

        if not await self._services.submission.is_published(submission_id):
            raise NotFoundUserException(f"Published submission '{submission_id}' was not found.")

        archive = await self._sync_provider.get_metadata_archive(submission_id)
        return Response(
            content=archive,
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{submission_id}.zip"'},
        )
