"""OIDC authentication API handler."""

from typing import cast

from aiohttp import web
from aiohttp.web import Request, Response

from ...services.auth_service import AuthServiceHandler


def get_authorized_user_id(req: Request) -> str:
    """
    Get the authorized user id.

    :param req: The HTTP request.
    :returns: The authorized user id.
    """
    if "user_id" not in req:
        raise web.HTTPUnauthorized(reason="Missing authorized user id.")
    return cast(str, req["user_id"])


def get_authorized_user_name(req: Request) -> str:
    """
    Get the authorized username.

    :param req: The HTTP request.
    :returns: The authorized username.
    """
    if "user_name" not in req:
        raise web.HTTPUnauthorized(reason="Missing authorized user name.")
    return cast(str, req["user_name"])


class AuthAPIHandler:
    """OIDC authentication API handler."""

    def __init__(self, service_handler: AuthServiceHandler) -> None:
        """OIDC authentication API handler."""

        self._service_handler = service_handler

    async def login(self, _: Request) -> web.HTTPSeeOther:
        """Redirect user to AAI login.

        :raises: HTTPInternalServerError if OIDC configuration init failed
        :returns: HTTPSeeOther redirect to AAI
        """

        return await self._service_handler.login()

    async def callback(self, req: Request) -> Response:
        """Handle the OIDC callback and redirect the user with a JWT token in the URL fragment.

        :param req: A HTTP request instance with callback parameters
        :return: A redirect response to the frontend app with the JWT token included in the URL fragment.
        """

        return await self._service_handler.callback(req)

    async def logout(self, _: Request) -> web.HTTPSeeOther:
        """Log the user out by clearing cookie.

        :returns: HTTPSeeOther redirect to login page
        """

        return await self._service_handler.logout()
