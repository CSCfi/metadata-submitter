"""OIDC service."""

import os
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import parse_qs, urlparse

import ujson
from aiohttp import ClientResponse, web
from aiohttp.web import Request, Response
from idpyoidc.client.rp_handler import RPHandler
from idpyoidc.exception import OidcMsgError
from yarl import URL

from ..api.services.auth import JWT_EXPIRATION, AuthService
from ..conf.oidc import oidc_config
from ..helpers.logger import LOG
from .service_handler import ServiceHandler


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
        # PKCE sessions for CLI users: state -> session info
        self._pkce_sessions: dict[str, dict[str, Any]] = {}

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
                            # "with_dpop_header": ["userinfo", "refresh_token"]  # optional
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

    async def login(self) -> web.HTTPSeeOther:
        """Redirect user to AAI login.

        :raises: HTTPInternalServerError if OIDC configuration init failed
        :returns: HTTPSeeOther redirect to AAI
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

        # Redirect user to AAI
        response = web.HTTPSeeOther(rph_session_url)
        response.headers["Location"] = rph_session_url
        return response

    async def callback(self, req: Request) -> Response:
        """Handle the OIDC callback and redirect the user with a JWT token in the URL fragment.

        This function completes the OpenID Connect (OIDC) authorization code flow. It exchanges
        the authorization code for tokens (ID token, access token), retrieves user information
        from the identity provider, creates an application-specific JWT, and then redirects
        the user to the frontend application with the JWT token appended in the URL fragment.

        The token is included as a URL fragment so that it is only accessible to client-side
        scripts and not sent to the server in future requests.

        :param req: A HTTP request instance with callback parameters

        # Returns:
            A redirect response to the frontend app with the JWT token included in the URL fragment.
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

        # Generate a JWT token.
        jwt_token = await AuthService.create_jwt_token_from_userinfo(session["userinfo"])

        LOG.info("OIDC redirect to %r", f"{self.redirect}/home")

        response = web.HTTPSeeOther(f"{self.redirect}/home")
        secure_cookie = os.environ.get("OIDC_SECURE_COOKIE", "").upper() != "FALSE"
        response.set_cookie(
            name="access_token",
            value=jwt_token,
            httponly=True,
            secure=secure_cookie,
            samesite="Strict",  # or "Lax" depending on your needs
            path="/",
            max_age=int(JWT_EXPIRATION.total_seconds()),
        )
        # Set access token cookie for Pouta access
        pouta_access_token = session["userinfo"].get("pouta_access_token", "").strip()
        response.set_cookie(
            name="pouta_access_token",
            value=pouta_access_token,
            httponly=True,
            secure=secure_cookie,
            samesite="Strict",  # or "Lax" depending on your needs
            path="/",
            max_age=int(JWT_EXPIRATION.total_seconds()),
        )
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-Cache"
        response.headers["Expires"] = "0"
        # done like this otherwise it will not redirect properly
        response.headers["Location"] = "/home" if self.redirect == self.domain else f"{self.redirect}/home"
        return response

    async def logout(self) -> web.HTTPSeeOther:
        """Log the user out by clearing cookie.

        :returns: HTTPSeeOther redirect to login page
        """
        response = web.HTTPSeeOther(f"{self.redirect}/")
        response.del_cookie("access_token", path="/")
        response.headers["Location"] = "/" if self.redirect == self.domain else f"{self.redirect}/"
        LOG.debug("Logged out user.")
        return response

    async def login_cli(self) -> web.Response:
        """Initiate PKCE Authorization Code Flow for CLI users.

        This endpoint initiates an Authorization Code Flow with PKCE, returning
        an OIDC authorization URL that the user should visit in their web browser.

        :returns: JSON response with authorization_url and instructions
        """
        try:
            # Get the authorization URL from RPHandler using CLI client config
            auth_url = self.rph.begin("aai")

            # Extract state from the generated URL to store our session
            parsed = urlparse(auth_url)
            params = parse_qs(parsed.query)
            state = params.get("state", [None])[0]

            if state:
                # Store session for callback verification
                session_info = {
                    "state": state,
                    "created_at": datetime.now(timezone.utc),
                    "expires_at": datetime.now(timezone.utc) + timedelta(minutes=5),
                    "token": None,  # Will be populated on first successful callback
                }
                self._pkce_sessions[state] = session_info
                LOG.info("PKCE CLI flow initiated for state: %s", state)

            return web.Response(text=f"\nComplete the login at:\n{auth_url}\n\n")

        except Exception as e:
            LOG.exception("Failed to initiate PKCE CLI flow: %r", e)
            raise web.HTTPInternalServerError(reason="Failed to initiate authentication")

    async def login_cli_callback(self, req: Request) -> web.Response:
        """Handle PKCE callback for CLI users.

        This endpoint receives the authorization code and state from the OIDC provider.
        The CLI can pass the full callback URL (including all query parameters) to this endpoint.

        :param req: The HTTP request with authorization code and state
        :returns: JSON response with access token
        """
        # Lazy cleanup of expired sessions if dict is growing
        if len(self._pkce_sessions) > 100:
            await self._cleanup_expired_pkce_sessions()

        # Get parameters from OIDC callback
        code = req.query.get("code")
        state = req.query.get("state")

        # Validate state and code
        if not code or not state:
            reason = "Missing code or state in callback."
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)

        # Look up PKCE session by state
        if state not in self._pkce_sessions:
            LOG.error("Unknown state in callback: %s", state)
            raise web.HTTPBadRequest(reason="Invalid or unknown state parameter.")

        pkce_session = self._pkce_sessions[state]

        # Check session expiration
        if datetime.now(timezone.utc) > pkce_session["expires_at"]:
            del self._pkce_sessions[state]
            LOG.error("PKCE session expired for state: %s", state)
            raise web.HTTPUnauthorized(reason="PKCE session has expired.")

        # If JWT was already created, return it to allow reuse of callback URL
        # for the duration of PKCE session without creating new JWTs unnecessarily.
        if pkce_session.get("token"):
            LOG.info("Reusing cached token for state: %s", state)
            return web.Response(text=f"{pkce_session['token']}")

        # Use RPHandler to finalize the flow
        try:
            session_info = self.rph.get_session_information(state)
            session_info["code"] = code
            # Finalize using the CLI client config
            session = self.rph.finalize(self.iss, session_info)
        except OidcMsgError as e:
            LOG.error("OIDC callback failed: %r", e)
            raise web.HTTPUnauthorized(reason="Token validation failed.")
        except Exception as e:
            LOG.error("Unexpected error during authentication: %r", e)
            raise web.HTTPInternalServerError(reason="Unexpected error during authentication.")

        # Generate JWT token
        jwt_token = await AuthService.create_jwt_token_from_userinfo(session["userinfo"])

        # Store token in session for reuse within expiration window
        self._pkce_sessions[state]["token"] = jwt_token
        self._pkce_sessions[state]["token_generated_at"] = datetime.now(timezone.utc)
        LOG.info("PKCE authorization flow completed successfully for state: %s", state)
        return web.Response(text=jwt_token)

    async def _cleanup_expired_pkce_sessions(self) -> None:
        """Clean up expired PKCE sessions.

        This is called periodically to prevent memory leaks from accumulating sessions.
        """
        now = datetime.now(timezone.utc)
        expired_states = [state for state, session in self._pkce_sessions.items() if now > session["expires_at"]]
        for state in expired_states:
            del self._pkce_sessions[state]
            LOG.debug("Cleaned up expired PKCE session: %s", state)

    @staticmethod
    async def healthcheck_callback(response: ClientResponse) -> bool:
        text_content = await response.text()
        content = ujson.loads(text_content)
        return "userinfo_endpoint" in content
