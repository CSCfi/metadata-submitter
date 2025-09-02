"""Handle HTTP methods for server."""

from aiohttp import web
from aiohttp.web import Request, StreamResponse

from ...helpers.logger import LOG
from ..auth import get_authorized_user_id
from ..resources import get_file_provider_service, get_project_service
from .restapi import RESTAPIHandler


class FilesAPIHandler(RESTAPIHandler):
    """API Handler for managing a project's files metadata."""

    async def get_project_buckets(self, request: Request) -> StreamResponse:
        """List all buckets in a specific project.

        :param request: GET request
        :returns: JSON response containing list of buckets
        """
        project_id = request.match_info["projectId"]
        project_service = get_project_service(request)
        file_service = get_file_provider_service(request)

        # Check that user is affiliated with the project.
        user_id = get_authorized_user_id(request)
        await project_service.verify_user_project(user_id, project_id)

        # TO DO: sort out project level differentiation for buckets in S3
        buckets = await file_service.list_buckets()
        LOG.info("Retrieved %d buckets for project %s.", len(buckets), project_id)
        return self._json_response(buckets)

    async def get_files_in_bucket(self, request: Request) -> StreamResponse:
        """List all files in a specific bucket from the file provider service.

        :param request: GET request
        :returns: JSON response containing submission ID for updated submission
        """
        project_id = request.match_info["projectId"]
        bucket = request.match_info["bucket"]
        project_service = get_project_service(request)
        file_service = get_file_provider_service(request)

        # Check that user is affiliated with the project.
        user_id = get_authorized_user_id(request)
        await project_service.verify_user_project(user_id, project_id)

        # TO DO: sort out project level differentiation for files in S3
        files = await file_service.list_files_in_bucket(bucket)
        LOG.info("Retrieved %d files in bucket %s.", len(files.root), bucket)
        return web.json_response(files.model_dump(mode="json"))
