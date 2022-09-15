"""Handle HTTP methods for server."""

import aiohttp_session
import ujson
from aiohttp import web
from aiohttp.web import Request, Response

from ...helpers.logger import LOG
from ..operators import UserOperator
from .restapi import RESTAPIHandler


class UserAPIHandler(RESTAPIHandler):
    """API Handler for users."""

    async def get_user(self, req: Request) -> Response:
        """Get one user by its user ID.

        :param req: GET request
        :raises: HTTPUnauthorized if not current user
        :returns: JSON response containing user object or list of user templates or user submissions by id
        """
        session = await aiohttp_session.get_session(req)

        user_id = req.match_info["userId"]
        if user_id != "current":
            LOG.info(f"User ID {user_id} was requested")
            raise web.HTTPUnauthorized(reason="Only current user retrieval is allowed")

        current_user = session["user_info"]

        # Return whole user object if templates or submissions are not specified in query
        db_client = req.app["db_client"]
        operator = UserOperator(db_client)
        user = await operator.read_user(current_user)
        LOG.info(f"GET user with ID {user_id} was successful.")
        return web.Response(
            body=ujson.dumps(user, escape_forward_slashes=False), status=200, content_type="application/json"
        )

    async def delete_user(self, req: Request) -> Response:
        """Delete user from database.

        :param req: DELETE request
        :raises: HTTPUnauthorized if not current user
        :returns: HTTPNoContent response
        """
        session = await aiohttp_session.get_session(req)

        user_id = req.match_info["userId"]
        if user_id != "current":
            LOG.info(f"User ID {user_id} delete was requested")
            raise web.HTTPUnauthorized(reason="Only current user deletion is allowed")
        db_client = req.app["db_client"]
        operator = UserOperator(db_client)

        current_user = session["user_info"]

        await operator.delete_user(current_user)
        LOG.info(f"DELETE user with ID {current_user} was successful.")

        session.invalidate()

        LOG.debug(f"Logged out user {user_id}")
        return web.HTTPNoContent()
