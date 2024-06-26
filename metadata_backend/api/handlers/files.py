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

        # Check that project exists
        project_op = ProjectOperator(db_client)
        await project_op.check_project_exists(data["projectId"])

        # Check that user is affiliated with project
        user_op = UserOperator(db_client)
        user_has_project = await user_op.check_user_has_project(data["projectId"], data["userId"])
        if not user_has_project:
            reason = f"user {data['userId']} is not affiliated with project {data['projectId']}"
            LOG.error(reason)
            raise web.HTTPUnauthorized(reason=reason)

        if not isinstance(data["files"], list):
            reason = "Field 'files' must be a list"
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)

        file_ids = []
        file_op = FileOperator(db_client)

        try:
            for file in data["files"]:
                new_file = File(
                    file["name"],
                    file["path"],
                    data["projectId"],
                    file["bytes"],
                    file["encrypted_checksums"],
                    file["unencrypted_checksums"],
                )
                file_id = await file_op._create_file(new_file)
                file_ids.append(file_id)

        except KeyError as file_key_error:
            reason = "Request payload content did not include all necessary details."
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason) from file_key_error

        return web.Response(body=ujson.dumps({"fileIds": file_ids}), status=201, content_type="application/json")
