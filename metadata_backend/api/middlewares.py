"""Middleware methods for server."""
import json
from typing import Callable

from aiohttp.web import HTTPError, HTTPException, Request, Response, middleware

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
            return _json_exception(error.status, error)

    return http_error_handler


def _json_exception(status: int, exception: HTTPException) -> Response:
    """Convert an HTTP exception into a problem detailed JSON response.

    The problem details are in accordance with RFC 7807.
    (https://tools.ietf.org/html/rfc7807)

    :param status: Status code of the HTTP exception
    :param exception: Exception content
    :returns: Response in JSON format
    """
    body = json.dumps({
        # 'type': ,
        # type would provide an URL to custom error document
        # it is optional and assumes "about:blank" if not provided
        'title': exception.text,
        'detail': exception.reason,  # FIX text and reason are the same
        # 'instance': ,
        # instance would provide the specific URL where the error was received
        # and is also optional
    }).encode('utf-8')
    LOG.info(str(body))
    return Response(status=status, body=body,
                    content_type='application/problem+json')
