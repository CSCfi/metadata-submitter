"""OIDC authentication API handler."""

from typing import cast

from aiohttp import web
from aiohttp.web import Request

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

        auth_url = await self._service_handler.get_oidc_auth_url()
        response = web.HTTPSeeOther(auth_url)
        response.headers["Location"] = auth_url
        return response

    async def callback(self, req: Request) -> web.HTTPSeeOther:
        """Handle the OIDC callback and redirect the user with a JWT token in the URL fragment.

        :param req: A HTTP request instance with callback parameters
        :return: A redirect response to the frontend app with the JWT token included in the URL fragment.
        """

        jwt, userinfo = await self._service_handler.callback(req)
        return await self._service_handler.initiate_web_session(jwt, userinfo)

    async def logout(self, _: Request) -> web.HTTPSeeOther:
        """Log the user out by clearing cookies.

        :returns: HTTPSeeOther redirect to login page
        """

        return await self._service_handler.logout()

    async def login_cli(self, _: Request) -> web.Response:
        """Return the OIDC authentication URL for CLI use case.

        :raises: HTTPInternalServerError if OIDC configuration init failed
        :returns: Text response with authorization_url
        """

        auth_url = await self._service_handler.get_oidc_auth_url()
        return web.Response(text=f"\nComplete the login at:\n{auth_url}\n\n")

    async def callback_cli(self, req: Request) -> web.Response:
        """Return the JWT token for CLI use case.

        :param req: The HTTP request with code and state parameters
        :returns: JSON response with access_token
        """

        jwt, _ = await self._service_handler.callback(req)
        return web.Response(text=f"\n{jwt}\n\n")
