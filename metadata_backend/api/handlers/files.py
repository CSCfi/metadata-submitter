"""Handle HTTP methods for server."""

import aiohttp_session
import ujson
from aiohttp import web

from ...helpers.logger import LOG
from ..operators.file import File, FileOperator
from ..operators.project import ProjectOperator
from ..operators.user import UserOperator
from .restapi import RESTAPIHandler


class FilesAPIHandler(RESTAPIHandler):
    """API Handler for managing a project's files metadata."""

    async def get_project_files(self, request: web.Request) -> web.StreamResponse:
        """Get files belonging to a project.

        :param request: GET request
        :returns: JSON response containing submission ID for updated submission
        """
        session = await aiohttp_session.get_session(request)

        project_id = self._get_param(request, name="projectId")
        db_client = request.app["db_client"]

        # Check that project exists
        project_op = ProjectOperator(db_client)
        await project_op.check_project_exists(project_id)

        user_operator = UserOperator(db_client)

        current_user = session["user_info"]
        user = await user_operator.read_user(current_user)
        user_has_project = await user_operator.check_user_has_project(project_id, user["userId"])
        if not user_has_project:
            reason = f"user {user['userId']} is not affiliated with project {project_id}"
            LOG.error(reason)
            raise web.HTTPUnauthorized(reason=reason)

        file_op = FileOperator(db_client)
        return self._json_response(await file_op.read_project_files(project_id))

    async def post_project_files(self, request: web.Request) -> web.Response:
        """Handle files post request.

        :param request: POST request
        :returns: JSON response containing a list of file IDs of created files
        """
        db_client = request.app["db_client"]
        data = await self._get_data(request)

        try:
            userId = data["userId"]
            projectId = data["projectId"]
            if isinstance(data["files"], list):
                files = data["files"]
            else:
                raise TypeError
        except (KeyError, TypeError) as exc:
            reason = (
                "Fields `userId`, `projectId`, `files` are required."
                if isinstance(exc, KeyError)
                else "Field `files` must be a list."
            )
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)

        # Check that project exists
        project_op = ProjectOperator(db_client)
        await project_op.check_project_exists(projectId)

        # Check that user is affiliated with project
        user_op = UserOperator(db_client)
        user_has_project = await user_op.check_user_has_project(projectId, userId)
        if not user_has_project:
            reason = f"user {userId} is not affiliated with project {projectId}"
            LOG.error(reason)
            raise web.HTTPUnauthorized(reason=reason)

        # Form file objects and validate against schema before creation
        file_op = FileOperator(db_client)
        validated_file_objects = []

        try:
            for file in files:
                new_file = File(
                    file["name"],
                    file["path"],
                    projectId,
                    file["bytes"],
                    file["encrypted_checksums"],
                    file["unencrypted_checksums"],
                )
                file_object = await file_op.form_validated_file_object(new_file)
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
        :raises HTTP Not Found if file not associated with submission
        :returns: HTTP No Content response
        """
        project_id = request.match_info["projectId"]
        db_client = request.app["db_client"]

        # Check that project exists
        project_op = ProjectOperator(db_client)
        await project_op.check_project_exists(project_id)

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
