"""Key API handler."""

from aiohttp import web
from aiohttp.web import Request, Response

from ..models.models import ApiKey
from .auth import get_authorized_user_id
from .restapi import RESTAPIHandler


class KeyAPIHandler(RESTAPIHandler):
    """Key API handler."""

    async def post_api_key(self, req: Request) -> Response:
        """
        Create and return a new API key for the authenticated user.

        The user must provide the key_id in the request json body.

        Args:
            req: The aiohttp request.

        Returns:
            Text response containing the new API key.
        """
        user_id = get_authorized_user_id(req)

        # Create and store the new API key.
        data = await req.json()

        api_key = await self._services.auth.create_api_key(user_id, ApiKey(**data).key_id)

        return web.Response(text=api_key, content_type="text/plain")

    async def delete_api_key(self, req: Request) -> Response:
        """
        Revoke an API key for the authenticated user.

        The user must provide the key_id in the request json body.

        Args:
            req: The aiohttp request.
        """
        user_id = get_authorized_user_id(req)

        # Remove and remove the API key.
        data = await req.json()

        await self._services.auth.revoke_api_key(user_id, ApiKey(**data).key_id)

        return web.Response(status=204)

    async def get_api_keys(self, req: Request) -> Response:
        """
        List all API keys for the authenticated user.

        Returns:
            JSON response containing the API keys.
        """
        user_id = get_authorized_user_id(req)

        body = [k.model_dump(mode="json") for k in await self._services.auth.list_api_keys(user_id)]

        return web.json_response(body)
