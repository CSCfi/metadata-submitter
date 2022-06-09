"""Middleware methods for server."""
import ujson
from http import HTTPStatus
from typing import Callable, Coroutine, Any, Awaitable
import aiohttp_session
import time

from aiohttp import web
from aiohttp.web import Request, Response, middleware
from yarl import URL

from ..helpers.logger import LOG
from ..conf.conf import aai_config

HTTP_ERROR_MESSAGE = "HTTP %r request to %r raised an HTTP %d exception."

AiohttpHandler = Callable[[web.Request], Coroutine[Awaitable, Any, web.Response]]


@middleware
async def http_error_handler(req: Request, handler: AiohttpHandler) -> Response:
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
    except (web.HTTPSuccessful, web.HTTPRedirection):
        # Catches 200s and 300s
        raise
    except web.HTTPError as error:
        # Catch 400s and 500s
        LOG.info(HTTP_ERROR_MESSAGE, req.method, req.path, error.status)
        problem = _json_problem(error, req.url)
        LOG.debug("Response payload is %r", problem)

        if error.status in {400, 401, 403, 404, 415, 422, 502, 504}:
            error.content_type = c_type
            error.text = problem
            raise error
        else:
            LOG.exception(HTTP_ERROR_MESSAGE + " This IS a bug.", req.method, req.path, error.status)
            raise web.HTTPInternalServerError(text=problem, content_type=c_type)
    except Exception:
        # We don't expect any other errors, so we log it and return a nice message instead of letting server crash
        LOG.exception("HTTP %r request to %r raised an unexpected exception. This IS a bug.", req.method, req.path)
        exception = web.HTTPInternalServerError(reason="Server ran into an unexpected error", content_type=c_type)
        problem = _json_problem(exception, req.url)
        exception.text = problem
        raise exception


@middleware
async def check_session_at(
    req: web.Request,
    handler: AiohttpHandler,
) -> web.Response:
    """Raise on expired sessions or invalid sessions.

    :param req: A request instance
    :param handler: A request handler
    :raises: Reformatted HTTP Exceptions
    :returns: Successful requests unaffected
    """
    main_paths = {
        "/aai",
        "/callback",
        "/static",
        "/swagger",
        "/health",
    }
    try:
        session = await aiohttp_session.get_session(req)
        LOG.debug(f"session: {session}")
        if not (req.path in main_paths):
            if not all(k in session for k in {"access_token", "user_info", "at"}):
                LOG.debug("checked session parameter")
                response = web.HTTPSeeOther(f"{aai_config['domain']}/aai")
                response.headers["Location"] = "/aai"
                session.invalidate()
                raise response
            if session["at"] + 28800 < time.time():
                session.invalidate()
                raise web.HTTPUnauthorized(
                    headers={"WWW-Authenticate": 'OAuth realm="/", charset="UTF-8"'}, reason="Token expired."
                )
    except KeyError as error:
        reason = f"No valid session. A session was invalidated due to invalid token. {error}"
        LOG.info(reason)
        raise web.HTTPUnauthorized(reason=reason)
    except Exception as error:
        reason = f"No valid session. A session was invalidated due to another reason: {error}"
        LOG.info(reason)
        raise web.HTTPUnauthorized(reason=reason)

    return await handler(req)


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
