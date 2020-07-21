"""Middleware methods for server."""
import json
import re
from http import HTTPStatus
from os import environ
from typing import Callable

from aiohttp import web
from aiohttp.web import Request, Response, middleware
from authlib.jose import jwt, errors
from yarl import URL

from ..helpers.logger import LOG


@middleware
async def http_error_handler(req: Request, handler: Callable) -> Response:
    """Middleware for handling exceptions recieved from the API methods.

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


@middleware
async def jwt_authentication(req: Request, handler: Callable) -> Response:
    """Middleware for validating and authenticating JSON web token.

    :param req: A request instance
    :param handler: A request handler
    :raises: HTTP Exception with status code 401 or 403
    :returns: Successful requests unaffected
    """
    if 'Authorization' in req.headers:
        # Check token exists
        try:
            scheme, token = req.headers.get('Authorization').split(' ')
            LOG.info('Auth token received.')
        except ValueError as err:
            raise web.HTTPUnauthorized(reason=f"Failure to read token: {err}")

        # Check token has proper scheme and was provided.
        if not re.match('Bearer', scheme):
            raise web.HTTPUnauthorized(reason="Invalid token scheme, "
                                              "Bearer required.")
        if token is None:
            raise web.HTTPUnauthorized(reason='Token cannot be empty.')

        # JWK and JWTClaims parameters for decoding
        key = environ.get('PUBLIC_KEY', None)
        # TODO: get Oauth2 public key
        # TODO: verify audience claim

        # Include claims that are required to be present
        # in the payload of the token
        claims_options = {
            "iss": {
                "essential": True,
                # TODO: add the proper issuer URLs here
                "values": ["haka_iss", "elixir_iss"]
            },
            "exp": {
                "essential": True
            }
        }

        # Decode and validate token
        try:
            claims = jwt.decode(token, key, claims_options=claims_options)
            claims.validate()
            LOG.info('Auth token decoded and validated.')

            # TODO: Retrieve GA4GH passports and process into permissions

            req["token"] = {"authenticated": True}
            return await handler(req)
        except errors.MissingClaimError as err:
            raise web.HTTPUnauthorized(reason=f"{err}")
        except errors.ExpiredTokenError as err:
            raise web.HTTPUnauthorized(reason=f"{err}")
        except errors.InvalidClaimError as err:
            raise web.HTTPForbidden(reason=f"Token contains {err}")
        except errors.BadSignatureError as err:
            raise web.HTTPUnauthorized(reason="Token signature is invalid"
                                              f", {err}")
        except errors.InvalidTokenError as err:
            raise web.HTTPUnauthorized(reason="Invalid authorization token"
                                              f": {err}")
    else:
        req["token"] = {"authenticated": False}
        return await handler(req)


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
