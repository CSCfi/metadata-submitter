"""Handle HTTP methods for server."""

import aiohttp_session
import ujson
from secrets import token_hex
from aiohttp import web
from aiohttp.web import Request, Response

from ...helpers.logger import LOG
from ..operators.user import UserOperator
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
            LOG.info("User ID: %r was requested", user_id)
            raise web.HTTPUnauthorized(reason="Only current user retrieval is allowed")

        current_user = session["user_info"]

        # Return whole user object if templates or submissions are not specified in query
        db_client = req.app["db_client"]
        operator = UserOperator(db_client)
        user = await operator.read_user(current_user)
        LOG.info("GET user with ID: %r was successful.", user_id)
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
            LOG.error("User ID: %r delete was requested, however the id is different than 'current'.", user_id)
            raise web.HTTPUnauthorized(reason="Only current user deletion is allowed")
        db_client = req.app["db_client"]
        operator = UserOperator(db_client)

        current_user = session["user_info"]

        await operator.delete_user(current_user)
        LOG.info("DELETE user with ID: %r was successful.", current_user)

        session.invalidate()

        LOG.debug("Logged out user ID: %r.", user_id)
        return web.HTTPNoContent()

    async def generate_new_key(self, req: Request) -> Response:
        """Generates a new signing key to be used in HMAC tokens.
        User can have only one signing key, requesting the endpoint again will overwrite the old key.

        :param req: GET request
        :raises: HTTPUnauthorized if not current user
        :returns: JSON response containing userid, a new signing key, and instructions
        """
        session = await aiohttp_session.get_session(req)

        user_id = req.match_info["userId"]
        if user_id != "current":
            LOG.info("User ID: %r was requested", user_id)
            raise web.HTTPUnauthorized(reason="Only current user retrieval is allowed")

        current_user = session["user_info"]  # userid

        # generate a new key and update the user profile with it, replacing existing keys
        new_signing_key = token_hex()
        db_client = req.app["db_client"]
        operator = UserOperator(db_client)
        update_operation = [
            {
                "op": "replace",
                "path": "/signingKey",
                "value": new_signing_key,
            }
        ]
        _ = await operator.update_user(current_user, update_operation)
        LOG.info("GET user/key with ID: %r was successful.", current_user)
        response = {
            "userId": current_user,
            "signingKey": new_signing_key,
            "instructions": "A signing key has been generated for you. "
            + "You can have only one signing key at a time. "
            + "Calling this endpoint again will deprecate this key and generate a new one. "
            + "Keep this key safe, as it can be used to access your profile. "
            + "Create a timestamp for the validity period, for example 'now+300'. "
            + "Sign a token with HMAC(timestamp+userId), signed with your signing key. "
            + "Use the token as a Bearer token with 'valid=timestamp' and 'userId=userId' query parameters. ",
        }
        return web.Response(
            body=ujson.dumps(response, escape_forward_slashes=False), status=200, content_type="application/json"
        )
