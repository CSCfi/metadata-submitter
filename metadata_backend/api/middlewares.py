"""Middleware methods for server."""

from http import HTTPStatus
from typing import Awaitable, Callable

import jwt
import ujson
from aiohttp import web
from aiohttp.web import AppKey
from pydantic import ValidationError
from yarl import URL

from ..helpers.logger import LOG
from .exceptions import NotFoundUserException, SystemException, UserErrors, UserException
from .services.auth import AuthService

AUTHORIZATION_COOKIE = "access_token"

HTTP_ERROR_MESSAGE = "HTTP %r request to %r raised an HTTP %d exception."
HTTP_ERROR_MESSAGE_BUG = "HTTP %r request to %r raised an HTTP %d exception. This IS a bug."

AUTH_SERVICE: AppKey[AuthService] = AppKey("auth_service")

Handler = Callable[[web.Request], Awaitable[web.StreamResponse]]


@web.middleware
async def http_error_handler(req: web.Request, handler: Handler) -> web.StreamResponse:
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
    except NotFoundUserException as e:
        not_found_exception = web.HTTPNotFound(reason=e.message, content_type=c_type)
        not_found_exception.text = _json_problem(not_found_exception, req.url)
        raise not_found_exception from e
    except UserException as e:
        user_exception = web.HTTPBadRequest(reason=e.message, content_type=c_type)
        problem = _json_problem(user_exception, req.url)
        user_exception.text = problem
        raise user_exception from e
    except SystemException as e:
        system_exception = web.HTTPInternalServerError(reason=e.message, content_type=c_type)
        system_exception.text = _json_problem(system_exception, req.url)
        raise system_exception from e
    except UserErrors as e:
        validation_exception = web.HTTPBadRequest(reason="User error", content_type=c_type)
        validation_exception.text = _json_problem(validation_exception, req.url, errors=e.messages)
        raise validation_exception from e
    except ValidationError as e:
        reason = "; ".join(f"{'.'.join(map(str, err['loc']))}: {err['msg']}" for err in e.errors())
        validation_exception = web.HTTPBadRequest(reason=reason, content_type=c_type)
        validation_exception.text = _json_problem(validation_exception, req.url)
        raise validation_exception from e
    except Exception as exc:
        # We don't expect any other errors, so we log it and return a nice message instead of letting server crash
        LOG.exception("HTTP %r request to %r raised an unexpected exception. This IS a bug.", req.method, req.path)
        exception = web.HTTPInternalServerError(
            reason=f"Server ran into an unexpected error: {str(exc)}", content_type=c_type
        )
        exception.text = _json_problem(exception, req.url)
        raise exception from exc


async def verify_authorization(
    access_service: AuthService, jwt_token: str | None, api_key: str | None
) -> tuple[str, str]:
    """
    Verify the jwt authorization token and returns the authorized user id.

    :param access_service: service to validate JWT tokens and API keys.
    :param jwt_token: The JWT token.
    :param api_key: The API key.
    :returns: Authorized user id and user name.
    """

    if jwt_token:
        try:
            # Verify the JWT token.
            return access_service.validate_jwt_token(jwt_token)
        except Exception as e:
            raise web.HTTPUnauthorized(reason=f"Authorization failed: {e}") from e
    elif api_key:
        try:
            # Verify the API key.
            user_id = await access_service.validate_api_key(api_key)
            return user_id, user_id  # User name is not stored for API keys.
        except Exception as e:
            raise web.HTTPUnauthorized(reason=f"Authorization failed: {e}") from e

    else:
        raise web.HTTPUnauthorized(reason="Missing JWT access token or API key")


@web.middleware
async def authorization(req: web.Request, handler: Handler) -> web.StreamResponse:
    """
    Middleware to check for a valid authorization token (JWT cookie or API key).

    Priority:
    1. JWT token: Secure HttpOnly cookie.
    2. API key: Authorization header with Bearer token.

    :param req: An aiohttp request
    :param handler: A request handler
    """

    if req.path.endswith("/health"):
        # No authorization required for health endpoint.
        return await handler(req)

    LOG.debug("Authorizing request")

    # Extract JWT token from the Secure HttpOnly cookie.
    jwt_token = req.cookies.get(AUTHORIZATION_COOKIE)

    if jwt_token is not None:
        LOG.debug("Found JWT Authorization token in cookie")

    #  Extract JWT token or API key from the Authorization header.
    api_key = None
    if not jwt_token:
        auth_header = req.headers.get("Authorization")
        if auth_header:
            parts = auth_header.split()
            if len(parts) == 2 and parts[0].lower() == "bearer":
                api_key_or_jwt_token = parts[1]

                try:
                    jwt.decode(api_key_or_jwt_token, options={"verify_signature": False})
                    jwt_token = api_key_or_jwt_token
                    LOG.debug("Found JWT Authorization token in Authorization header")
                except Exception:
                    api_key = api_key_or_jwt_token
                    LOG.debug("Found API key in Authorization header")

    auth_service: AuthService = req.app[AUTH_SERVICE]

    req["user_id"], req["user_name"] = await verify_authorization(auth_service, jwt_token, api_key)

    LOG.debug("Successfully authorized request")

    return await handler(req)


def _json_problem(
    exception: web.HTTPError, url: URL, _type: str = "about:blank", errors: list[str] | None = None
) -> str:
    """Convert an HTTP exception into a problem detailed JSON object.

    The problem details are in accordance with RFC 7807.
    (https://tools.ietf.org/html/rfc7807)

    :param exception: an HTTPError exception
    :param url: Request URL that caused the exception
    :param _type: Url to a document describing the error
    :returns: Problem detail JSON object as a string
    """
    _problem = {
        # Replace type value with an URL to
        # a custom error document when one exists
        "type": _type,
        "title": HTTPStatus(exception.status).phrase,
        "detail": exception.reason,
        "status": exception.status,
        "instance": url.path,
    }
    # we require the additional members to be sent as dict
    # so that we can easily append them to pre-formatted response
    if exception.text != exception.reason and exception.content_type == "application/json":
        # we use the content to append to extend application/problem+json
        # response, with additional members
        # typecasting necessary for mypy
        _problem.update(ujson.loads(str(exception.text)))

    if errors:
        _problem["errors"] = errors

    body = ujson.dumps(
        _problem,
        escape_forward_slashes=False,
    )
    return body
