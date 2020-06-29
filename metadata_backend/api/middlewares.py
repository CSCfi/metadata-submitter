"""Middleware methods for server."""
import json
from http import HTTPStatus
from typing import Callable

from aiohttp import web
from aiohttp.web import Request, Response, middleware
from yarl import URL

from ..helpers.logger import LOG


def error_middleware() -> Callable:
    """Middleware for handling exceptions recieved from the API methods.

    :returns: Handled response
    """

    @middleware
    async def http_error_handler(req: Request, handler: Callable) -> Response:
        """Handle HTTP errors.

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
            c_type = 'application/problem+json'
            if error.status == 400:
                raise web.HTTPBadRequest(text=details,
                                         content_type=c_type)
            elif error.status == 401:
                raise web.HTTPUnauthorized(text=details,
                                           content_type=c_type)
            elif error.status == 403:
                raise web.HTTPForbidden(text=details,
                                        content_type=c_type)
            elif error.status == 404:
                raise web.HTTPNotFound(text=details,
                                       content_type=c_type)
            else:
                raise web.HTTPServerError()

    return http_error_handler


def _json_exception(status: int, exception: web.HTTPException,
                    url: URL) -> str:
    """Convert an HTTP exception into a problem detailed JSON object.

    The problem details are in accordance with RFC 7807.
    (https://tools.ietf.org/html/rfc7807)

    :param status: Status code of the HTTP exception
    :param exception: Exception content
    :param url: Request URL that caused the exception
    :returns: Problem detail JSON object as a string
    """
    body = json.dumps({
        'type': "about:blank",
        # Replace type value above with an URL to
        # a custom error document when one exists
        'title': HTTPStatus(status).phrase,
        'detail': exception.reason,
        'instance': url.path,  # optional
    })
    return body
