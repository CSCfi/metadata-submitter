"""Handle HTTP methods for server."""
import aiohttp_session
from aiohttp import web

from ...helpers.logger import LOG
from ..operators.file import FileOperator
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
