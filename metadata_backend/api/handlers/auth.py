"""OIDC authentication API handler."""

from fastapi import Query, Request
from fastapi.responses import PlainTextResponse, RedirectResponse
from starlette import status

from ...services.auth_service import OIDC_PROFILE_CLI, OIDC_PROFILE_WEB, AuthServiceHandler


class AuthAPIHandler:
    """OIDC authentication API handler."""

    def __init__(self, service_handler: AuthServiceHandler) -> None:
        """OIDC authentication API handler."""

        self._service_handler = service_handler

    async def login(self) -> RedirectResponse:
        """Login using the OIDC Authorization Code flow."""

        auth_url = await self._service_handler.get_oidc_auth_url(OIDC_PROFILE_WEB)

        return RedirectResponse(
            url=auth_url,
            status_code=status.HTTP_303_SEE_OTHER,
        )

    async def callback(
        self,
        state: str = Query(..., description="The OIDC Authorization Code flow `state` parameter."),
        code: str = Query(..., description="The OIDC Authorization Code flow `code` parameter."),
    ) -> RedirectResponse:
        """The OIDC Authorization Code flow callback."""

        jwt, userinfo = await self._service_handler.callback(state, code)
        return await self._service_handler.initiate_web_session(jwt, userinfo)

    async def logout(self, _: Request) -> RedirectResponse:
        """Logout and redirect to the login page."""

        return await self._service_handler.logout()

    async def login_cli(self, _: Request) -> PlainTextResponse:
        """Login a CLI user using the OIDC Authorization Code flow."""

        auth_url = await self._service_handler.get_oidc_auth_url(OIDC_PROFILE_CLI)
        return PlainTextResponse(content=f"\nComplete the login at:\n{auth_url}\n\n")

    async def callback_cli(
        self,
        state: str = Query(..., description="The OIDC Authorization Code flow `state` parameter."),
        code: str = Query(..., description="The OIDC Authorization Code flow `code` parameter."),
    ) -> PlainTextResponse:
        """The OIDC Authorization Code flow callback for a CLI user."""

        jwt, _ = await self._service_handler.callback(state, code)
        return PlainTextResponse(content=f"\n{jwt}\n\n")
