"""Handle Access for request and OIDC workflow."""

import hashlib
import ujson

from aiohttp import web
from aiohttp.web import Request, Response
from .middlewares import decrypt_cookie, generate_cookie
from .operators import UserOperator
from oidcrp.rp_handler import RPHandler
from oidcrp.exception import OidcServiceError

from typing import Dict, Tuple

from ..helpers.logger import LOG


class AccessHandler:
    """Handler for user access methods."""

    def __init__(self, aai: Dict) -> None:
        """Define AAI variables and paths.

        :param aai: dictionary with AAI specific config
        """
        self.domain = aai["domain"]
        self.redirect = aai["redirect"]
        self.client_id = aai["client_id"]
        self.client_secret = aai["client_secret"]
        self.callback_url = aai["callback_url"]
        self.oidc_url = aai["oidc_url"].rstrip("/") + "/.well-known/openid-configuration"
        self.iss = aai["oidc_url"]
        self.scope = aai["scope"]
        self.auth_method = aai["auth_method"]

        self.oidc_conf = {
            "aai": {
                "issuer": self.iss,
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "redirect_uris": [self.callback_url],
                "behaviour": {
                    "response_types": self.auth_method.split(" "),
                    "scope": self.scope.split(" "),
                },
            },
        }
        self.rph = RPHandler(self.oidc_url, client_configs=self.oidc_conf)

    async def login(self, req: Request) -> Response:
        """Redirect user to AAI login.

        :param req: A HTTP request instance (unused)
        :raises: HTTPSeeOther redirect to login AAI
        """
        LOG.debug("Start login")

        # Generate authentication payload
        session = self.rph.begin("aai")

        # Redirect user to AAI
        response = web.HTTPSeeOther(session["url"])
        response.headers["Location"] = session["url"]
        raise response

    async def callback(self, req: Request) -> Response:
        """Include correct tokens in cookies as a callback after login.

        Sets session information such as access_token and user_info.
        Sets encrypted cookie to identify clients.

        :raises: HTTPBadRequest in case login failed
        :raises: HTTPForbidden in case of bad session
        :param req: A HTTP request instance with callback parameters
        :returns: HTTPSeeOther redirect to home page
        """

        # Response from AAI must have the query params `state` and `code`
        if "state" in req.query and "code" in req.query:
            LOG.debug("AAI response contained the correct params.")
            params = {"state": req.query["state"], "code": req.query["code"]}
        else:
            reason = f"AAI response is missing mandatory params, received: {req.query}"
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)

        # Verify oidc_state and retrieve auth session
        session = None
        try:
            session = self.rph.get_session_information(params["state"])
        except KeyError as e:
            LOG.error(f"Session not initialised: {e}")
            raise web.HTTPForbidden(reason="Bad user session.")

        # Place authorization_code to session for finalize step
        session["auth_request"]["code"] = params["code"]

        # finalize requests id_token and access_token with code, validates them and requests userinfo data
        try:
            session = self.rph.finalize(session["iss"], session["auth_request"])
        except OidcServiceError as e:
            LOG.error(f"OIDC Callback failed with: {e}")
            raise web.HTTPBadRequest(reason="Invalid OIDC callback.")

        response = web.HTTPSeeOther(f"{self.redirect}/home")

        cookie, _ = generate_cookie(req)

        cookie["referer"] = req.url.host
        cookie["signature"] = (
            hashlib.sha256((cookie["id"] + cookie["referer"] + req.app["Salt"]).encode("utf-8"))
        ).hexdigest()

        cookie_crypted = req.app["Crypt"].encrypt(ujson.dumps(cookie).encode("utf-8")).decode("utf-8")

        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-Cache"
        response.headers["Expires"] = "0"

        trust = False if self.domain.startswith("http://localhost:5430") else True

        response.set_cookie(
            name="MTD_SESSION",
            value=cookie_crypted,
            max_age=3600,
            secure=trust,  # type: ignore
            httponly=trust,  # type: ignore
        )

        # Inject cookie to this request to let _set_user work as expected.

        session_id = cookie["id"]

        req.app["Session"][session_id] = {"oidc_state": params["state"], "access_token": session["token"]}
        req.app["Cookies"].add(session_id)

        user_data: Tuple[str, str]
        if "eppn" in session["userinfo"]:
            user_data = (
                session["userinfo"]["eppn"],
                f"{session['userinfo']['given_name']} {session['userinfo']['family_name']}",
            )
        elif "sub" in session["userinfo"]:
            user_data = (
                session["userinfo"]["sub"],
                f"{session['userinfo']['given_name']} {session['userinfo']['family_name']}",
            )
        await self._set_user(req, session_id, user_data)

        # done like this otherwise it will not redirect properly
        response.headers["Location"] = "/home" if self.redirect == self.domain else f"{self.redirect}/home"

        LOG.debug(f"cookie MTD_SESSION set {cookie_crypted}")
        return response

    async def logout(self, req: Request) -> Response:
        """Log the user out by revoking tokens.

        :param req: A HTTP request instance
        :raises: HTTPBadRequest in case logout failed
        :returns: HTTPSeeOther redirect to login page
        """
        # Revoke token at AAI
        # Implement, when revocation_endpoint is supported by AAI

        try:
            cookie = decrypt_cookie(req)
            req.app["OIDC_State"].remove(req.app["Session"][cookie["id"]]["oidc_state"])
        except KeyError:
            pass

        try:
            cookie = decrypt_cookie(req)
            req.app["Session"].pop(cookie["id"])
        except KeyError:
            pass

        response = web.HTTPSeeOther(f"{self.redirect}/")
        response.headers["Location"] = "/" if self.redirect == self.domain else f"{self.redirect}/"
        LOG.debug("Logged out user ")

        raise response

    async def _set_user(self, req: Request, session_id: str, user_data: Tuple[str, str]) -> None:
        """Set user in current session and return user id based on result of create_user.

        :raises: HTTPBadRequest in could not get user info from AAI OIDC
        :param req: A HTTP request instance
        :param user_data: user id and given name
        """
        LOG.debug("Create and set user to database")

        db_client = req.app["db_client"]
        operator = UserOperator(db_client)
        user_id = await operator.create_user(user_data)
        req.app["Session"][session_id]["user_info"] = user_id
