"""Handle HTTP methods for server."""

from aiohttp import web
from aiohttp.web import Request, StreamResponse

from ...helpers.logger import LOG
from ..auth import get_authorized_user_id
from ..resources import get_file_provider_service, get_project_service
from .restapi import RESTAPIHandler


class FilesAPIHandler(RESTAPIHandler):
    """API Handler for managing a project's files metadata."""

    async def get_project_folders(self, request: Request) -> StreamResponse:
        """List all folders in a specific project.

        :param request: GET request
        :returns: JSON response containing list of folders
        """
        project_id = request.match_info["projectId"]
        project_service = get_project_service(request)
        file_service = get_file_provider_service(request)

        # Check that user is affiliated with the project.
        user_id = get_authorized_user_id(request)
        await project_service.verify_user_project(user_id, project_id)

        # TO DO: sort out project level differentiation for folders in S3
        folders = await file_service.list_folders()
        LOG.info("Retrieved %d folders for project %s.", len(folders), project_id)
        return self._json_response(folders)

    async def get_files_in_folder(self, request: Request) -> StreamResponse:
        """List all files in a specific folder from the file provider service.

        :param request: GET request
        :returns: JSON response containing submission ID for updated submission
        """
        project_id = request.match_info["projectId"]
        folder = request.match_info["folder"]
        project_service = get_project_service(request)
        file_service = get_file_provider_service(request)

        # Check that user is affiliated with the project.
        user_id = get_authorized_user_id(request)
        await project_service.verify_user_project(user_id, project_id)

        # TO DO: sort out project level differentiation for files in S3
        files = await file_service.list_files_in_folder(folder)
        LOG.info("Retrieved %d files in folder %s.", len(files.root), folder)
        return web.json_response(files.model_dump(mode="json"))
