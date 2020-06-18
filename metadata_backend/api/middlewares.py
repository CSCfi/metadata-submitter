"""Middleware methods for server."""
import json
from typing import Callable

from aiohttp.web import HTTPError, Request, Response, middleware


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


def _json_exception(status: int, exception: Exception) -> Response:
    """Convert an HTTP exception into JSON response.

    :param status: Status code of the HTTP exception
    :param exception: Exception content
    :returns: Response in JSON format
    """
    body = json.dumps({
        'error': status,
        'detail': str(exception)
    }).encode('utf-8')
    return Response(status=status, body=body,
                    content_type='application/json')
