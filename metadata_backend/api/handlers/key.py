"""Key API handler."""

from typing import Annotated

from fastapi import Body, Response, status
from fastapi.responses import PlainTextResponse

from ..dependencies import UserDependency
from ..models.models import ApiKey
from .restapi import RESTAPIHandler

ApiKeyBody = Annotated[ApiKey, Body(description="API key")]


class KeyAPIHandler(RESTAPIHandler):
    """Key API handler."""

    async def create_api_key(self, user: UserDependency, key: ApiKeyBody) -> PlainTextResponse:
        """Create a new API key."""

        # Create and store the new API key.
        api_key = await self._services.auth.create_api_key(user.user_id, key.key_id)
        return PlainTextResponse(content=f"\n{api_key}\n\n")

    async def delete_api_key(self, key: ApiKeyBody, user: UserDependency) -> Response:
        """Delete an API key."""

        # Remove and remove the API key.
        await self._services.auth.revoke_api_key(user.user_id, key.key_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    async def get_api_keys(self, user: UserDependency) -> list[ApiKey]:
        """List API keys owner by the user."""

        return await self._services.auth.list_api_keys(user.user_id)
