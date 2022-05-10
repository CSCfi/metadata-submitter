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


AiohttpHandler = Callable[[web.Request], Coroutine[Awaitable, Any, web.Response]]


def _check_error_page_requested(req: Request, error_code: int) -> web.Response:  # type:ignore
    """Return the correct error page with correct status code."""
    if "Accept" in req.headers and req.headers["Accept"]:
        if req.headers["Accept"].split(",")[0] in {"text/html", "application/xhtml+xml"}:
            raise web.HTTPSeeOther(
                f"/error{str(error_code)}",
                headers={
                    "Cache-Control": "no-cache, no-store, must-revalidate",
                    "Pragma": "no-cache",
                    "Expires": "0",
                    "Location": f"/error{str(error_code)}",
                },
            )


@middleware
async def http_error_handler(req: Request, handler: AiohttpHandler) -> Response:
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
            _check_error_page_requested(req, 400)
            raise web.HTTPBadRequest(text=details, content_type=c_type)
        elif error.status == 401:
            _check_error_page_requested(req, 401)
            raise web.HTTPUnauthorized(
                headers={"WWW-Authenticate": 'OAuth realm="/", charset="UTF-8"'}, text=details, content_type=c_type
            )
        elif error.status == 403:
            _check_error_page_requested(req, 403)
            raise web.HTTPForbidden(text=details, content_type=c_type)
        elif error.status == 404:
            _check_error_page_requested(req, 404)
            raise web.HTTPNotFound(text=details, content_type=c_type)
        elif error.status == 415:
            _check_error_page_requested(req, 400)
            raise web.HTTPUnsupportedMediaType(text=details, content_type=c_type)
        elif error.status == 422:
            _check_error_page_requested(req, 400)
            raise web.HTTPUnprocessableEntity(text=details, content_type=c_type)
        else:
            _check_error_page_requested(req, 500)
            raise web.HTTPInternalServerError(text=details, content_type=c_type)


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
        "/health",
        "/error401",
        "/error403",
        "/error404",
        "/error500",
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


def _json_exception(status: int, exception: web.HTTPException, url: URL) -> str:
    """Convert an HTTP exception into a problem detailed JSON object.

    The problem details are in accordance with RFC 7807.
    (https://tools.ietf.org/html/rfc7807)

    :param status: Status code of the HTTP exception
    :param exception: Exception content
    :param url: Request URL that caused the exception
    :returns: Problem detail JSON object as a string
    """
    body = ujson.dumps(
        {
            "type": "about:blank",
            # Replace type value above with an URL to
            # a custom error document when one exists
            "title": HTTPStatus(status).phrase,
            "detail": exception.reason,
            "instance": url.path,  # optional
        },
        escape_forward_slashes=False,
    )
    return body
