"""Middleware methods for server."""
import json
from http import HTTPStatus
from typing import Callable

from aiohttp.web import HTTPError, HTTPException, Request, Response, middleware
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
        :returns: JSON response for the error
        """
        try:
            response = await handler(req)
            return response
        except HTTPError as error:
            return _json_exception(error.status, error, req.url)

    return http_error_handler


def _json_exception(status: int, exception: HTTPException,
                    url: URL) -> Response:
    """Convert an HTTP exception into a problem detailed JSON response.

    The problem details are in accordance with RFC 7807.
    (https://tools.ietf.org/html/rfc7807)

    :param status: Status code of the HTTP exception
    :param exception: Exception content
    :param url: Request URL that caused the exception
    :returns: Response in problem detail JSON format
    """
    body = json.dumps({
        'type': "about:blank",
        # Replace type value above with an URL to
        # a custom error document when one exists
        'title': HTTPStatus(status).phrase,
        'detail': exception.reason,
        'instance': url.path,  # optional and can be removed
    }).encode('utf-8')
    LOG.info(str(body))
    return Response(status=status, body=body,
                    content_type='application/problem+json')
