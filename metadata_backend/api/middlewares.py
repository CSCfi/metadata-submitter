"""Middleware methods for server."""
import json
from http import HTTPStatus
from typing import Callable, Dict, Tuple

from aiohttp import web, ClientSession
from aiohttp.web import Request, Response, middleware, StreamResponse
from multidict import CIMultiDict
from yarl import URL
import os
import secrets
import hashlib

from ..helpers.logger import LOG
from ..conf.conf import aai_config


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
            raise web.HTTPBadRequest(text=details, content_type=c_type)
        elif error.status == 401:
            raise web.HTTPUnauthorized(
                headers={"WWW-Authenticate": 'Bearer realm="/", charset="UTF-8"'}, text=details, content_type=c_type
            )
        elif error.status == 403:
            raise web.HTTPForbidden(text=details, content_type=c_type)
        elif error.status == 404:
            raise web.HTTPNotFound(text=details, content_type=c_type)
        elif error.status == 415:
            raise web.HTTPUnsupportedMediaType(text=details, content_type=c_type)
        else:
            raise web.HTTPServerError()


@middleware
async def check_login(request: Request, handler: Callable) -> StreamResponse:
    """Check login if there is a username."""
    if (
        request.path
        in [
            "/schemas",
            "/drafts",
            "/validate",
            "/submit",
            "/folders",
            "/objects",
            "/users",
            "/logout",
            "/home",
            "newdraft",
        ]
        and "OIDC_URL" in os.environ
        and bool(os.getenv("OIDC_URL"))
    ):
        session = request.app["Session"]
        if "access_token" not in session:
            raise web.HTTPSeeOther(location="/aai")
        if decrypt_cookie(request)["id"] in request.app["Cookies"]:
            _check_csrf(request)
        else:
            LOG.debug("Cannot find cookie in session")
            raise web.HTTPUnauthorized(headers={"WWW-Authenticate": 'Bearer realm="/", charset="UTF-8"'})
        return await handler(request)
    else:
        return await handler(request)


def generate_cookie(request: Request) -> Tuple[dict, str]:
    """
    Generate an encrypted and unencrypted cookie.

    Returns a tuple containing both the unencrypted and encrypted cookie.
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
    """Decrypt a cookie using the server instance specific fernet key."""
    if "MTD_SESSION" not in request.cookies:
        LOG.debug("Cannot find MTD_SESSION cookie")
        raise web.HTTPUnauthorized()
    cookie_json = request.app["Crypt"].decrypt(request.cookies["MTD_SESSION"].encode("utf-8")).decode("utf-8")
    cookie = json.loads(cookie_json)
    LOG.debug("Decrypted cookie: {0}".format(cookie))
    return cookie


def _check_csrf(request: web.Request) -> bool:
    """Check that the signature matches and referrer is correct."""
    cookie = decrypt_cookie(request)
    # Throw if the cookie originates from incorrect referer (meaning the
    # site's wrong)
    if "Referer" in request.headers.keys():
        # Pass referer check if we're returning from the login.
        if request.headers["Referer"] in aai_config["referer"]:
            LOG.info("Skipping Referer check due to request coming from OIDC.")
            return True
        if cookie["referer"] not in request.headers["Referer"]:
            LOG.info("Throw due to invalid referer: {0}".format(request.headers["Referer"]))
            raise web.HTTPForbidden()
    else:
        LOG.debug("Skipping referral validation due to missing Referer-header.")
    # Throw if the cookie signature doesn't match (meaning the referer might
    # have been changed without setting the signature)
    if not secrets.compare_digest(
        hashlib.sha256((cookie["id"] + cookie["referer"] + request.app["Salt"]).encode("utf-8")).hexdigest(),
        cookie["signature"],
    ):
        LOG.info("Throw due to invalid referer: {0}".format(request.headers["Referer"]))
        raise web.HTTPForbidden()
    # If all is well, return True.
    return True


async def get_userinfo(req: Request) -> Dict[str, str]:
    """Get information from userinfo endpoint."""
    token = ""
    try:
        session = req.app["Session"]
        if "access_token" not in session:
            raise web.HTTPSeeOther(location="/aai")

        token = session["access_token"]
    except Exception as e:
        LOG.error(f"Could not get session because of: {e}")
        raise web.HTTPBadRequest(reason="Could not get a proper session.")

    try:
        headers = CIMultiDict({"Authorization": f"Bearer {token}"})
        async with ClientSession(headers=headers) as sess:
            async with sess.get(f"{aai_config['user_info']}") as resp:
                result = await resp.json()
                return result
    except Exception as e:
        LOG.error(f"Could not get information from AAI UserInfo endpoint because of: {e}")
        raise web.HTTPBadRequest(reason="Could not get information from AAI UserInfo endpoint.")


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
