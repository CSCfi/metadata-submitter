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
        errors = []
        try:
            response = await handler(req)
        except HTTPError as error:
            errors.append(_json_exception(error.status, error, req.url))
        finally:
            if errors:
                # get error status code and remove it from the dict
                for e in errors:
                    status = e.pop('status', None)
                # insert array under errors key
                body = json.dumps({
                    'errors': errors
                }).encode('utf-8')
                return Response(status=status,
                                body=body,
                                content_type='application/problem+json')
            else:
                return response

    return http_error_handler


def _json_exception(status: int, exception: HTTPException, url: URL) -> dict:
    """Convert an HTTP exception into a problem detailed JSON object.

    The problem details are in accordance with RFC 7807.
    (https://tools.ietf.org/html/rfc7807)

    :param status: Status code of the HTTP exception
    :param exception: Exception content
    :param url: Request URL that caused the exception
    :returns: Dictionary of problem details
    """
    body = {'type': "about:blank",
            # Replace type value above with an URL to
            # a custom error document when one exists
            'title': HTTPStatus(status).phrase,
            'detail': exception.reason,
            'instance': url.path,  # instance is optional
            'status': status}
    LOG.info(str(body))
    return body
