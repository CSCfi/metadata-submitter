"""OIDC service."""

import os
from pathlib import Path
from typing import Any

import ujson
from aiohttp import ClientResponse, web
from aiohttp.web import Request
from idpyoidc.client.rp_handler import RPHandler
from idpyoidc.exception import OidcMsgError
from yarl import URL

from ..api.services.auth import JWT_EXPIRATION, AuthService
from ..conf.oidc import oidc_config
from ..helpers.logger import LOG
from .service_handler import ServiceHandler

private_jwk_path = Path(__file__).parent.parent.parent / "private" / "private_jwks.json"


class AuthServiceHandler(ServiceHandler):
    """OIDC service."""

    def __init__(self) -> None:
        """OIDC service."""

        self._config = oidc_config()

        super().__init__(
            service_name="auth",
            base_url=URL(self._config.OIDC_URL.rstrip("/")),
            healthcheck_url=URL(self._config.OIDC_URL) / ".well-known" / "openid-configuration",
            healthcheck_callback=self.healthcheck_callback,
        )

        self.domain = self._config.BASE_URL
        self.redirect = self._config.REDIRECT_URL
        self.client_id = self._config.OIDC_CLIENT_ID
        self.client_secret = self._config.OIDC_CLIENT_SECRET
        self.callback_url = self._config.callback_url
        self.oidc_url = self._config.OIDC_URL.rstrip("/") + "/.well-known/openid-configuration"
        self.iss = self._config.OIDC_URL
        self.scope = self._config.OIDC_SCOPE
        self.auth_method = "code"
        self._rph: RPHandler | None = None
        self.jwk_path = str(private_jwk_path)

    @property
    def rph(self) -> RPHandler:
        if self._rph is None:
            self._rph = RPHandler(self.oidc_url, client_configs=self.get_client_configs())
        return self._rph

    def get_client_configs(self) -> dict[str, dict[str, Any]]:
        return {
            "aai": {
                "issuer": self.iss,
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "client_type": "oidc",
                "redirect_uris": [self.callback_url],
                "key_conf": {"private_path": self.jwk_path, "key_defs": []},
                "behaviour": {
                    "response_types": self.auth_method.split(" "),
                    "scope": self.scope.split(" "),
                },
                "add_ons": {
                    "dpop": {
                        "function": "idpyoidc.client.oauth2.add_on.dpop.add_support",
                        "kwargs": {
                            "dpop_signing_alg_values_supported": [
                                "ES256",
                                "ES512",
                            ],
                        },
                    },
                    "pkce": {
                        "function": "idpyoidc.client.oauth2.add_on.pkce.add_support",
                        "kwargs": {
                            "code_challenge_length": 64,
                            "code_challenge_method": "S256",
                        },
                    },
                },
            },
        }

    async def get_oidc_auth_url(self) -> str:
        """Redirect user to AAI login.

        :raises: HTTPInternalServerError if OIDC configuration init failed
        :returns: OIDC Authorization URL
        """
        LOG.debug("Start login")

        # Generate authentication payload
        try:
            rph_session_url = self.rph.begin("aai")
        except Exception as e:
            # This can be caused if config is improperly configured, and
            # idpyoidc is unable to fetch oidc configuration from the given URL
            LOG.exception("OIDC authorization request failed with: %r", e)
            raise web.HTTPInternalServerError(reason="OIDC authorization request failed.")

        return str(rph_session_url)

    async def callback(self, req: Request) -> tuple[str, dict[str, Any]]:
        """Handle the OIDC callback and return application-specific JWT.

        This function completes the OpenID Connect (OIDC) authorization code flow with DPoP.
        It exchanges the authorization code for DPoP-bound tokens, retrieves user information
        and creates an application-specific JWT.

        :param req: A HTTP request instance with callback parameters
        :returns: JWT token as a string
        """

        # Response from AAI must have the query params `state` and `code`
        if "state" in req.query and "code" in req.query:
            params = {"state": req.query["state"], "code": req.query["code"]}
        else:
            reason = f"AAI response is missing mandatory params, received: {req.query}"
            LOG.error(reason)
            raise web.HTTPUnauthorized(reason=reason)

        # Verify oidc_state and retrieve auth session
        try:
            session_info = self.rph.get_session_information(params["state"])
        except KeyError as e:
            # This exception is raised if the RPHandler doesn't have the supplied "state"
            LOG.exception("Session not initialised, failed with: %r", e)
            raise web.HTTPUnauthorized(reason="Bad user session.")

        # Place authorization_code to session for finalize step
        session_info["code"] = params["code"]

        # finalize requests id_token and access_token with code, validates them and requests userinfo data
        try:
            session = self.rph.finalize(self.iss, session_info)
        except KeyError as e:
            LOG.exception("Issuer: %s not found, failed with: %r.", session_info["iss"], e)
            raise web.HTTPBadRequest(reason="Token issuer not found.")
        except OidcMsgError as e:
            # This exception is raised if RPHandler encounters an error due to:
            # 1. "code" is wrong, so token request failed
            # 2. token validation failed
            # 3. userinfo request failed
            LOG.exception("OIDC Callback failed with: %r", e)
            raise web.HTTPUnauthorized(reason="Invalid OIDC callback.")

        # Generate a JWT token for application authentication
        jwt = await AuthService.create_jwt_token_from_userinfo(session["userinfo"])
        return jwt, session["userinfo"]

    async def initiate_web_session(self, jwt_token: str, userinfo: dict[str, Any]) -> web.HTTPSeeOther:
        """
        Initiate web session by setting JWT token in secure cookie.

        :param jwt_token: The JWT token to be set in the cookie
        :param userinfo: The user information dictionary
        :return: HTTPSeeOther redirect to the home page
        """
        LOG.info("OIDC redirect to %r", f"{self.redirect}/home")

        response = web.HTTPSeeOther(f"{self.redirect}/home")
        secure_cookie = os.environ.get("OIDC_SECURE_COOKIE", "").upper() != "FALSE"

        # Set the application JWT token
        response.set_cookie(
            name="access_token",
            value=jwt_token,
            httponly=True,
            secure=secure_cookie,
            samesite="Strict",
            path="/",
            max_age=int(JWT_EXPIRATION.total_seconds()),
        )
        # TODO(improve): Remove pouta_access_token from session cookies.
        # Instead fetch it from /userinfo whenever needed.
        pouta_access_token = userinfo.get("pouta_access_token", "").strip()
        response.set_cookie(
            name="pouta_access_token",
            value=pouta_access_token,
            httponly=True,
            secure=secure_cookie,
            samesite="Strict",
            path="/",
            max_age=int(JWT_EXPIRATION.total_seconds()),
        )
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-Cache"
        response.headers["Expires"] = "0"
        response.headers["Location"] = "/home" if self.redirect == self.domain else f"{self.redirect}/home"
        return response

    async def logout(self) -> web.HTTPSeeOther:
        """Log the user out by clearing all cookies.

        :returns: HTTPSeeOther redirect to login page
        """
        response = web.HTTPSeeOther(f"{self.redirect}/")
        response.del_cookie("access_token", path="/")
        response.del_cookie("pouta_access_token", path="/")
        response.headers["Location"] = "/" if self.redirect == self.domain else f"{self.redirect}/"
        LOG.debug("Logged out user and cleared all cookies.")
        return response

    @staticmethod
    async def healthcheck_callback(response: ClientResponse) -> bool:
        text_content = await response.text()
        content = ujson.loads(text_content)
        return "userinfo_endpoint" in content
