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
            if response.status == 404:
                return _json_exception(response.status,
                                       Exception(response.message))
            return response
        except HTTPError as error:
            return _json_exception(error.status, error)

        # If something else goes wrong, convert to Internal Server Error
        # except Exception as ex:
            # return _json_exception(500, ex)

    return http_error_handler


def _json_exception(status: int, exception: Exception) -> Response:
    """Convert an HTTP exception into JSON response.

    :param status: Status code of the HTTP exception
    :param exception: Exception content
    :returns: Response in JSON format
    """
    body = json.dumps({
        'error': exception.__class__.__name__,
        'detail': str(exception)
    }).encode('utf-8')
    return Response(status=status, body=body,
                    content_type='application/json')
