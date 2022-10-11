"""Middleware methods for server."""
import time
from http import HTTPStatus
from typing import List

import aiohttp_session
import ujson
from aiohttp import web
from yarl import URL

from ..conf.conf import aai_config
from ..helpers.logger import LOG
from .auth import AAIServiceHandler, AccessHandler, ProjectList, UserData

HTTP_ERROR_MESSAGE = "HTTP %r request to %r raised an HTTP %d exception."
HTTP_ERROR_MESSAGE_BUG = "HTTP %r request to %r raised an HTTP %d exception. This IS a bug."


@web.middleware
async def http_error_handler(req: web.Request, handler: aiohttp_session.Handler) -> web.StreamResponse:
    """Middleware for handling exceptions received from the API methods.

    :param req: A request instance
    :param handler: A request handler
    :raises: Reformatted HTTP Exceptions
    :returns: Successful requests unaffected
    """
    c_type = "application/problem+json"
    try:
        response = await handler(req)
        return response
    except web.HTTPRedirection:
        # Catches 300s
        raise
    except web.HTTPError as error:
        # Catch 400s and 500s
        LOG.exception(HTTP_ERROR_MESSAGE, req.method, req.path, error.status)
        problem = _json_problem(error, req.url)
        LOG.debug("Response payload is %r", problem)

        if error.status in {400, 401, 403, 404, 405, 415, 422, 502, 504}:
            error.content_type = c_type
            error.text = problem
            raise error
        LOG.exception(HTTP_ERROR_MESSAGE_BUG, req.method, req.path, error.status)
        raise web.HTTPInternalServerError(text=problem, content_type=c_type)
    except Exception as exc:
        # We don't expect any other errors, so we log it and return a nice message instead of letting server crash
        LOG.exception("HTTP %r request to %r raised an unexpected exception. This IS a bug.", req.method, req.path)
        exception = web.HTTPInternalServerError(reason="Server ran into an unexpected error", content_type=c_type)
        problem = _json_problem(exception, req.url)
        exception.text = problem
        raise exception from exc


@web.middleware
async def check_session(req: web.Request, handler: aiohttp_session.Handler) -> web.StreamResponse:
    """Raise on expired sessions or invalid sessions.

    :param req: A request instance
    :param handler: A request handler
    :raises: Reformatted HTTP Exceptions
    :returns: Successful requests unaffected
    """
    try:
        session = await aiohttp_session.get_session(req)
        LOG.debug("Identified session: %r", session)

        if session.empty:
            if "Authorization" in req.headers:
                session = await create_session_with_token(req)
                if session.empty:
                    raise _unauthorized("Invalid access token.")
            else:
                session.invalidate()
                raise _unauthorized("You must provide authentication to access SD-Submit API.")

        if not all(k in session for k in ["access_token", "user_info", "at", "oidc_state"]):
            LOG.error("Checked session parameter, session is invalid %r. This could be a bug or abuse.", session)
            session.invalidate()
            raise _unauthorized("Invalid session, authenticate again.")

        if session["at"] + 28800 < time.time():
            session.invalidate()
            raise _unauthorized("Token expired.")

    except KeyError as error:
        reason = f"No valid session. A session was invalidated due to invalid token. {error}"
        LOG.exception(reason)
        raise _unauthorized(reason) from error
    except web.HTTPException:
        # HTTPExceptions are processed in the other middleware
        raise
    except Exception as error:
        reason = f"No valid session. A session was invalidated due to another reason: {error}"
        LOG.exception("No valid session. A session was invalidated due to another reason")
        raise _unauthorized(reason) from error

    return await handler(req)


def _unauthorized(reason: str) -> web.HTTPUnauthorized:
    return web.HTTPUnauthorized(headers={"WWW-Authenticate": 'OAuth realm="/", charset="UTF-8"'}, reason=reason)


def _json_problem(exception: web.HTTPError, url: URL, _type: str = "about:blank") -> str:
    """Convert an HTTP exception into a problem detailed JSON object.

    The problem details are in accordance with RFC 7807.
    (https://tools.ietf.org/html/rfc7807)

    :param exception: an HTTPError exception
    :param url: Request URL that caused the exception
    :param _type: Url to a document describing the error
    :returns: Problem detail JSON object as a string
    """
    body = ujson.dumps(
        {
            # Replace type value with an URL to
            # a custom error document when one exists
            "type": _type,
            "title": HTTPStatus(exception.status).phrase,
            "detail": exception.reason,
            "status": exception.status,
            "instance": url.path,  # optional
        },
        escape_forward_slashes=False,
    )
    return body


async def create_session_with_token(req: web.Request) -> aiohttp_session.Session:
    """Create an authenticated session for the duration of a single request by using an access token.

    :param req: request object containing database connection and request headers
    :returns: session cookie
    """
    session = await aiohttp_session.get_session(req)

    # Get bearer token from Authorization header
    header = req.headers.get("Authorization", "")
    header_parts: List[str] = header.split(" ")
    if len(header_parts) == 2:
        if header_parts[0] != "Bearer":
            return session  # current empty session
    else:
        return session  # current empty session

    # we need to create a new instance every time, this is not something we can re-use
    aai = AAIServiceHandler()
    aai.service_name = "aai_for_single_session_token_auth"
    # Get path to userinfo from OIDC config
    oidc_config = await aai._request(method="GET", path="/.well-known/openid-configuration")
    if not oidc_config or "userinfo_endpoint" not in oidc_config:
        return session  # current empty session

    # Validate token by sending it to AAI userinfo and getting back user profile
    headers = {"Authorization": f"Bearer {header_parts[1]}"}
    aai.base_url = oidc_config["userinfo_endpoint"]
    aai.http_client_headers = headers
    userinfo = await aai._request(method="GET")
    if not userinfo:
        return session  # current empty session

    await aai.http_client_close()

    # Parse user profile data from userinfo endpoint response, these steps can raise 401
    single_session: AccessHandler = AccessHandler(aai_config)
    user_data: UserData = await single_session._create_user_data(userinfo)
    projects: ProjectList = await single_session._get_projects_from_userinfo(userinfo)
    user_data["projects"] = await single_session._process_projects(req, projects)

    # Create session with required keys
    session_cookie = await aiohttp_session.new_session(req)
    session_cookie["at"] = time.time()
    session_cookie["oidc_state"] = "unused"
    session_cookie["access_token"] = header_parts[1]
    session_cookie["user_info"] = await single_session._set_user(req, session_cookie, user_data)

    return session_cookie  # validated session
