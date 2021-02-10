"""Middleware methods for server."""
import json
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


def _check_error_page_requested(req: Request, error_code: int) -> web.Response:  # type:ignore
    """Return the correct error page with correct status code."""
    if "Accept" in req.headers and req.headers["Accept"]:
        if req.headers["Accept"].split(",")[0] in ["text/html", "application/xhtml+xml"]:
            raise web.HTTPSeeOther(
                f"/error{str(error_code)}",
                content_type="text/html",
                headers={"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache", "Expires": "0"},
            )


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
        details = _json_exception(error.status, error, req.url)
        LOG.error(details)
        c_type = "application/problem+json"
        if error.status == 400:
            _check_error_page_requested(req, 500)
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
            _check_error_page_requested(req, 500)
            raise web.HTTPUnsupportedMediaType(text=details, content_type=c_type)
        elif error.status == 422:
            _check_error_page_requested(req, 500)
            raise web.HTTPUnprocessableEntity(text=details, content_type=c_type)
        else:
            _check_error_page_requested(req, 500)
            raise web.HTTPServerError()


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
        "/validate",
        "/publish",
        "/submit",
        "/folders",
        "/objects",
        "/users",
        "/logout",
        "/home",
        "/newdraft",
    ]
    main_paths = ["/aai", "/callback", "/static", "/health"]
    if (
        request.path.startswith(tuple(main_paths))
        or request.path == "/"
        or (request.path.startswith("/") and request.path.endswith(tuple([".svg", ".jpg", ".ico", ".json"])))
    ):
        return await handler(request)
    if request.path.startswith(tuple(controlled_paths)) and "OIDC_URL" in os.environ and bool(os.getenv("OIDC_URL")):
        session = request.app["Session"]
        if not all(x in ["access_token", "user_info", "oidc_state"] for x in session):
            LOG.debug("checked session parameter")
            response = web.HTTPSeeOther(f"{aai_config['domain']}/aai")
            response.headers["Location"] = "/aai"
            raise response
        if decrypt_cookie(request)["id"] in request.app["Cookies"]:
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
    return (cookie, request.app["Crypt"].encrypt(json.dumps(cookie).encode("utf-8")).decode("utf-8"))


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
        cookie = json.loads(cookie_json)
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
        if "auth_referer" in aai_config and request.headers["Referer"].startswith(aai_config["auth_referer"]):
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


def _json_exception(status: int, exception: web.HTTPException, url: URL) -> str:
    """Convert an HTTP exception into a problem detailed JSON object.

    The problem details are in accordance with RFC 7807.
    (https://tools.ietf.org/html/rfc7807)

    :param status: Status code of the HTTP exception
    :param exception: Exception content
    :param url: Request URL that caused the exception
    :returns: Problem detail JSON object as a string
    """
    body = json.dumps(
        {
            "type": "about:blank",
            # Replace type value above with an URL to
            # a custom error document when one exists
            "title": HTTPStatus(status).phrase,
            "detail": exception.reason,
            "instance": url.path,  # optional
        }
    )
    return body
