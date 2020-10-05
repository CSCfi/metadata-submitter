"""Middleware methods for server."""
import json
from http import HTTPStatus
from typing import Callable, Dict

from aiohttp import web, ClientSession
from aiohttp.web import Request, Response, middleware, StreamResponse
from aiohttp_session import get_session
from multidict import CIMultiDict
from yarl import URL
import os

from ..helpers.logger import LOG
from ..conf.conf import aai_config


@middleware
async def http_error_handler(req: Request, handler: Callable) -> Response:
    """Middleware for handling exceptions received from the API methods.

    :param req: A request instance
    :param handler: A request handler
    :raises: Reformatted HTTP Exceptions
    :returns: Successful requests unaffected
    """
    try:
        response = await handler(req)
        return response
    except web.HTTPError as error:
        details = _json_exception(error.status, error, req.url)
        LOG.error(details)
        c_type = "application/problem+json"
        if error.status == 400:
            raise web.HTTPBadRequest(text=details, content_type=c_type)
        elif error.status == 401:
            raise web.HTTPUnauthorized(text=details, content_type=c_type)
        elif error.status == 403:
            raise web.HTTPForbidden(text=details, content_type=c_type)
        elif error.status == 404:
            raise web.HTTPNotFound(text=details, content_type=c_type)
        elif error.status == 415:
            raise web.HTTPUnsupportedMediaType(text=details, content_type=c_type)
        else:
            raise web.HTTPServerError()


@middleware
async def check_login(request: Request, handler: Callable) -> StreamResponse:
    """Check login if there is a username."""
    if request.path not in ["/aai", "/callback"] and "OIDC_URL" in os.environ and bool(os.getenv("OIDC_URL")):
        session = await get_session(request)
        token = session.get("access_token")
        logged = request.cookies.get("logged_in")
        if not (token and logged):
            raise web.HTTPSeeOther(location="/aai")

        return await handler(request)
    else:
        return await handler(request)


async def get_userinfo(req: Request) -> Dict[str, str]:
    """Get information from userinfo endpoint."""
    token = ""
    try:
        session = await get_session(req)
        token = session["access_token"]
    except Exception as e:
        LOG.error(f"Could not get session because of: {e}")
        raise web.HTTPBadRequest(reason="Could not get a proper session.")

    try:
        headers = CIMultiDict({"Authorization": f"Bearer {token}"})
        async with ClientSession(headers=headers) as sess:
            async with sess.get(f"{aai_config['user_info']}") as resp:
                result = await resp.json()
                return result
    except Exception as e:
        LOG.error(f"Could not get information from AAI UserInfo endpoint because of: {e}")
        raise web.HTTPBadRequest(reason="Could not get information from AAI UserInfo endpoint.")


def _json_exception(status: int, exception: web.HTTPException, url: URL) -> str:
    """Convert an HTTP exception into a problem detailed JSON object.

    The problem details are in accordance with RFC 7807.
    (https://tools.ietf.org/html/rfc7807)

    :param status: Status code of the HTTP exception
    :param exception: Exception content
    :param url: Request URL that caused the exception
    :returns: Problem detail JSON object as a string
    """
    body = json.dumps(
        {
            "type": "about:blank",
            # Replace type value above with an URL to
            # a custom error document when one exists
            "title": HTTPStatus(status).phrase,
            "detail": exception.reason,
            "instance": url.path,  # optional
        }
    )
    return body
