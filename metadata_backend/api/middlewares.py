"""Middleware methods for server."""
import ujson
from http import HTTPStatus
from typing import Callable, Tuple
from cryptography.fernet import InvalidToken

from aiohttp import web
from aiohttp.web import Request, Response, middleware, StreamResponse
from yarl import URL
import os
import secrets
import hashlib

from ..helpers.logger import LOG
from ..conf.conf import aai_config

HTTP_ERROR_MESSAGE = "HTTP %r request to %r raised an HTTP %d exception."


@middleware
async def http_error_handler(req: Request, handler: Callable) -> Response:
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
        LOG.info(HTTP_ERROR_MESSAGE, req.method, req.path, error.status)
        problem = _json_problem(error, req.url)
        LOG.debug("Response payload is %r", problem)
        c_type = "application/problem+json"

        if error.status in {400, 401, 403, 404, 415, 422}:
            error.content_type = c_type
            error.text = problem
            raise error
        else:
            LOG.exception(HTTP_ERROR_MESSAGE + " This IS a bug.", req.method, req.path, error.status)
            raise web.HTTPInternalServerError(text=problem, content_type=c_type)


@middleware
async def check_login(request: Request, handler: Callable) -> StreamResponse:
    """Check login if session user is logged in and can access API.

    :param req: A request instance
    :param handler: A request handler
    :raises: HTTPSeeOther in case session does not contain access token and user_info
    :raises: HTTPUnauthorized in case cookie cannot be found
    :returns: Successful requests unaffected
    """
    controlled_paths = [
        "/schemas",
        "/drafts",
        "/templates",
        "/validate",
        "/publish",
        "/submit",
        "/submissions",
        "/objects",
        "/users",
        "/logout",
        "/home",
        "/newdraft",
    ]
    main_paths = [
        "/aai",
        "/callback",
        "/static",
        "/swagger",
        "/health",
        "/error400",
        "/error401",
        "/error403",
        "/error404",
        "/error500",
    ]
    if (
        request.path.startswith(tuple(main_paths))
        or request.path == "/"
        or (request.path.startswith("/") and request.path.endswith(tuple([".svg", ".jpg", ".ico", ".json"])))
    ):
        return await handler(request)
    if request.path.startswith(tuple(controlled_paths)) and "OIDC_URL" in os.environ and bool(os.getenv("OIDC_URL")):
        cookie = decrypt_cookie(request)
        session = request.app["Session"].setdefault(cookie["id"], {})
        if not all(x in {"access_token", "user_info", "oidc_state"} for x in session):
            LOG.debug("checked session parameter")
            response = web.HTTPSeeOther(f"{aai_config['domain']}/aai")
            response.headers["Location"] = "/aai"
            raise response

        if cookie["id"] in request.app["Cookies"]:
            LOG.debug("checked cookie session")
            _check_csrf(request)
        else:
            LOG.debug("Cannot find cookie in session")
            raise web.HTTPUnauthorized(headers={"WWW-Authenticate": 'OAuth realm="/", charset="UTF-8"'})

        return await handler(request)
    elif "OIDC_URL" in os.environ and bool(os.getenv("OIDC_URL")):
        LOG.debug(f"not authorised to view this page {request.path}")
        raise web.HTTPUnauthorized(headers={"WWW-Authenticate": 'OAuth realm="/", charset="UTF-8"'})
    else:
        return await handler(request)


def get_session(request: Request) -> dict:
    """
    Return the current session for the user (derived from the cookie).

    :param request: A HTTP request instance
    :returns: a dict for the session.
    """
    cookie = decrypt_cookie(request)
    session = request.app["Session"].setdefault(cookie["id"], {})
    return session


def generate_cookie(request: Request) -> Tuple[dict, str]:
    """
    Generate an encrypted and unencrypted cookie.

    :param request: A HTTP request instance
    :returns: a tuple containing both the unencrypted and encrypted cookie.
    """
    cookie = {
        "id": secrets.token_hex(64),
        "referer": None,
        "signature": None,
    }
    # Return a tuple of the session as an encrypted JSON string, and the
    # cookie itself
    return (cookie, request.app["Crypt"].encrypt(ujson.dumps(cookie).encode("utf-8")).decode("utf-8"))


def decrypt_cookie(request: web.Request) -> dict:
    """Decrypt a cookie using the server instance specific fernet key.

    :param request: A HTTP request instance
    :raises: HTTPUnauthorized in case cookie not in request or invalid token
    :returns: decrypted cookie
    """
    if "MTD_SESSION" not in request.cookies:
        LOG.debug("Cannot find MTD_SESSION cookie")
        raise web.HTTPUnauthorized()
    try:
        cookie_json = request.app["Crypt"].decrypt(request.cookies["MTD_SESSION"].encode("utf-8")).decode("utf-8")
        cookie = ujson.loads(cookie_json)
        LOG.debug(f"Decrypted cookie: {cookie}")
        return cookie
    except InvalidToken:
        LOG.info("Throw due to invalid token.")
        raise web.HTTPUnauthorized()


def _check_csrf(request: web.Request) -> bool:
    """Check that the signature matches and referrer is correct.

    :raises: HTTPForbidden in case signature does not match
    :param request: A HTTP request instance
    """
    cookie = decrypt_cookie(request)
    # Throw if the cookie originates from incorrect referer (meaning the
    # site's wrong)
    if "Referer" in request.headers.keys():
        # Pass referer check if we're returning from the login.
        if "redirect" in aai_config and request.headers["Referer"].startswith(aai_config["redirect"]):
            LOG.info("Skipping Referer check due to request coming from frontend.")
            return True
        if "oidc_url" in aai_config and request.headers["Referer"].startswith(aai_config["oidc_url"]):
            LOG.info("Skipping Referer check due to request coming from OIDC.")
            return True
        if cookie["referer"] not in request.headers["Referer"]:
            LOG.info(f"Throw due to invalid referer: {request.headers['Referer']}")
            raise web.HTTPForbidden()
    else:
        LOG.debug("Skipping referral validation due to missing Referer-header.")
    # Throw if the cookie signature doesn't match (meaning the referer might
    # have been changed without setting the signature)
    if not secrets.compare_digest(
        hashlib.sha256((cookie["id"] + cookie["referer"] + request.app["Salt"]).encode("utf-8")).hexdigest(),
        cookie["signature"],
    ):
        LOG.info(f"Throw due to invalid referer: {request.headers['Referer']}")
        raise web.HTTPForbidden()
    # If all is well, return True.
    return True


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
