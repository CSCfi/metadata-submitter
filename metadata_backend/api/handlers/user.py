"""Project API handlers."""

from aiohttp import web
from aiohttp.web import Request, Response

from ..auth import get_authorized_user_id, get_authorized_user_name
from ..models.models import User
from ..resources import get_project_service


async def get_user(req: Request) -> Response:
    """
    Return projects for the authenticated user.

    Args:
        req: The aiohttp request.

    Returns:
        Projects.
    """
    user_id = get_authorized_user_id(req)
    user_name = get_authorized_user_name(req)

    project_service = get_project_service(req)

    user = User(
        user_id=user_id,
        user_name=user_name,
        projects=await project_service.get_user_projects(user_id),
    )

    return web.json_response(user.model_dump(mode="json"))
