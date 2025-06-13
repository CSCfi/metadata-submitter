"""Handle HTTP methods for server."""

import ujson
from aiohttp import web

from ...helpers.logger import LOG
from ..auth import get_authorized_user_id
from ..operators.file import File, FileOperator
from ..services.project import ProjectService
from .restapi import RESTAPIHandler


class FilesAPIHandler(RESTAPIHandler):
    """API Handler for managing a project's files metadata."""

    async def get_project_files(self, request: web.Request) -> web.StreamResponse:
        """Get files belonging to a project.

        :param request: GET request
        :returns: JSON response containing submission ID for updated submission
        """
        user_id = get_authorized_user_id(request)

        project_id = self._get_param(request, name="projectId")
        db_client = request.app["db_client"]
        project_service: ProjectService = request.app["project_service"]

        # Check that user is affiliated with the project.
        await project_service.verify_user_project(user_id, project_id)

        file_op = FileOperator(db_client)
        return self._json_response(await file_op.read_project_files(project_id))

    async def post_project_files(self, request: web.Request) -> web.Response:
        """Handle files post request.

        :param request: POST request
        :raises: HTTP Bad Request if response body format is invalid
        :raises: HTTP Unauthorized if user not affiliated with project
        :returns: JSON response containing a list of file IDs of created files
        """
        user_id = get_authorized_user_id(request)

        db_client = request.app["db_client"]
        project_service: ProjectService = request.app["project_service"]

        data = await self._get_data(request)
        is_bigpicture = request.query.get("is_bigpicture", "").strip().lower() == "true"

        try:
            project_id = data["projectId"]
            if isinstance(data["files"], list):
                files = data["files"]
            else:
                raise TypeError
        except (KeyError, TypeError) as exc:
            reason = (
                "Fields `projectId`, `files` are required."
                if isinstance(exc, KeyError)
                else "Field `files` must be a list."
            )
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)

        # Check that user is affiliated with the project.
        await project_service.verify_user_project(user_id, project_id)

        # Form file objects and validate against schema before creation
        file_op = FileOperator(db_client)
        validated_file_objects = []

        try:
            for file in files:
                new_file = File(
                    file["name"],
                    file["path"],
                    project_id,
                    file["bytes"],
                    file["encrypted_checksums"],
                    file["unencrypted_checksums"],
                )
                file_object = await file_op.form_validated_file_object(new_file, is_bigpicture)
                validated_file_objects.append(file_object)
        except KeyError as file_key_error:
            reason = "Fields `path`, `name`, `bytes`, `encrypted_checksums`, `unencrypted_checksums` are required."
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason) from file_key_error

        # Create files
        created_files = []

        for file in validated_file_objects:
            id_and_v = await file_op.create_file_or_version(file)
            created_files.append(id_and_v)

        return web.Response(body=ujson.dumps(created_files), status=201, content_type="application/json")

    async def delete_project_files(self, request: web.Request) -> web.Response:
        """Remove a file from a project.

        :param request: DELETE request
        :raises: HTTP Bad Request if response body format is invalid
        :raises: HTTP Unauthorized if user not affiliated with project
        :returns: HTTP No Content response
        """
        user_id = get_authorized_user_id(request)

        project_id = request.match_info["projectId"]

        db_client = request.app["db_client"]
        project_service: ProjectService = request.app["project_service"]

        # Check that user is affiliated with the project.
        await project_service.verify_user_project(user_id, project_id)

        data = await self._get_data(request)

        if not isinstance(data, list):
            reason = "Deleting files must be passed as a list of file paths."
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)

        # Check file exists in database
        file_operator = FileOperator(db_client)
        for file_path in data:
            if not isinstance(file_path, str):
                reason = "File path must be a string"
                LOG.error(reason)
                raise web.HTTPBadRequest(reason=reason)
            file = await file_operator.check_file_exists(project_id, file_path)
            if file is not None:
                await file_operator.flag_file_deleted(file)

        LOG.info(
            "DELETE files in project %s with file paths: %s was successful.",
            project_id,
            "\n".join(file_path for file_path in data),
        )
        return web.HTTPNoContent()
