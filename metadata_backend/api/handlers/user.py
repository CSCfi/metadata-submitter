"""User API handler."""

from aiohttp import web
from aiohttp.web import Request, Response

from ..models.models import User
from .auth import get_authorized_user_id, get_authorized_user_name
from .restapi import RESTAPIHandler


class UserAPIHandler(RESTAPIHandler):
    """User API handler."""

    async def get_user(self, req: Request) -> Response:
        """
        Return user information for the authenticated user.

        Args:
            req: The HTTP request.

        Returns:
            Projects.
        """
        user_id = get_authorized_user_id(req)
        user_name = get_authorized_user_name(req)

        user = User(
            user_id=user_id,
            user_name=user_name,
            projects=await self._services.project.get_user_projects(user_id),
        )

        return web.json_response(user.model_dump(mode="json"))
