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

        # List all buckets and filter those with the correct bucket policy.
        buckets = await file_service.list_buckets(project_id)
        LOG.info("Retrieved %d buckets available for project %s.", len(buckets), project_id)
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

        files = await file_service.list_files_in_bucket(bucket, project_id)
        LOG.info("Retrieved %d files in bucket %s.", len(files.root), bucket)
        return web.json_response(files.model_dump(mode="json"))

    async def grant_access_to_bucket(self, request: Request) -> StreamResponse:
        """Grant access to a specific bucket in a project.

        :param request: PUT request
        :returns: JSON response indicating success or failure
        """
        project_id = request.match_info["projectId"]
        bucket = request.match_info["bucket"]
        project_service = get_project_service(request)
        file_service = get_file_provider_service(request)

        # Check that user is affiliated with the project.
        user_id = get_authorized_user_id(request)
        await project_service.verify_user_project(user_id, project_id)

        # Grant access to the bucket.
        await file_service.update_bucket_policy(bucket, project_id)
        LOG.info("Granted access to bucket %s in project %s.", bucket, project_id)
        return web.Response(status=200)

    async def check_bucket_access(self, request: Request) -> StreamResponse:
        """Check if a specific bucket in a project is accessible.

        :param request: HEAD request
        :returns: Empty response with status 200 if accessible, 404 if not
        """
        project_id = request.match_info["projectId"]
        bucket = request.match_info["bucket"]
        project_service = get_project_service(request)
        file_service = get_file_provider_service(request)

        # Check that user is affiliated with the project.
        user_id = get_authorized_user_id(request)
        await project_service.verify_user_project(user_id, project_id)

        # Check that the bucket has been assigned the correct policy.
        has_access = await file_service.verify_bucket_policy(bucket, project_id)
        if not has_access:
            reason = f"Bucket {bucket} is not accessible in project {project_id}."
            LOG.error(reason)
            raise web.HTTPBadRequest()

        LOG.info("Bucket policy for bucket %s in project %s exists.", bucket, project_id)
        return web.Response(status=200)
