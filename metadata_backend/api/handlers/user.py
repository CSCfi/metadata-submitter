"""Handle HTTP methods for server."""

import ujson
from aiohttp import web
from aiohttp.web import Request, Response

from ...conf.conf import aai_config
from ...helpers.logger import LOG
from .restapi import RESTAPIHandler
from ..middlewares import decrypt_cookie, get_session
from ..operators import UserOperator


class UserAPIHandler(RESTAPIHandler):
    """API Handler for users."""

    async def get_user(self, req: Request) -> Response:
        """Get one user by its user ID.

        :param req: GET request
        :raises: HTTPUnauthorized if not current user
        :returns: JSON response containing user object or list of user templates or user folders by id
        """
        user_id = req.match_info["userId"]
        if user_id != "current":
            LOG.info(f"User ID {user_id} was requested")
            raise web.HTTPUnauthorized(reason="Only current user retrieval is allowed")

        current_user = get_session(req)["user_info"]

        # Return whole user object if templates or folders are not specified in query
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
        user_id = req.match_info["userId"]
        if user_id != "current":
            LOG.info(f"User ID {user_id} delete was requested")
            raise web.HTTPUnauthorized(reason="Only current user deletion is allowed")
        db_client = req.app["db_client"]
        operator = UserOperator(db_client)

        current_user = get_session(req)["user_info"]

        await operator.delete_user(current_user)
        LOG.info(f"DELETE user with ID {current_user} was successful.")

        cookie = decrypt_cookie(req)

        try:
            req.app["Session"].pop(cookie["id"])
            req.app["Cookies"].remove(cookie["id"])
        except KeyError:
            pass

        response = web.HTTPSeeOther(f"{aai_config['redirect']}/")
        response.headers["Location"] = (
            "/" if aai_config["redirect"] == aai_config["domain"] else f"{aai_config['redirect']}/"
        )
        LOG.debug("Logged out user ")
        raise response
