"""Handle Access for request and OIDC workflow."""

import os
import time
from typing import Any, Optional, cast

from aiohttp import ClientTimeout, web
from aiohttp.client_exceptions import ClientConnectorError, InvalidURL
from aiohttp.web import Request, Response
from idpyoidc.client.rp_handler import RPHandler
from idpyoidc.exception import OidcMsgError
from yarl import URL

from ..conf.conf import aai_config
from ..helpers.logger import LOG
from ..services.service_handler import ServiceHandler
from .services.auth import JWT_EXPIRATION, AccessService


def get_authorized_user_id(req: Request) -> str:
    """
    Get the authorized user id.

    :param req: The aiohttp request.
    :returns: The authorized user id.
    """
    if "user_id" not in req:
        raise web.HTTPUnauthorized(reason="Missing authorized user id.")
    return cast(str, req["user_id"])


def get_authorized_user_name(req: Request) -> str:
    """
    Get the authorized user name.

    :param req: The aiohttp request.
    :returns: The authorized user name.
    """
    if "user_name" not in req:
        raise web.HTTPUnauthorized(reason="Missing authorized user name.")
    return cast(str, req["user_name"])


class AccessHandler:
    """Handler for user access methods."""

    def __init__(self, aai: dict[str, Any]) -> None:
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
                "client_type": "oidc",
                "redirect_uris": [self.callback_url],
                "behaviour": {
                    "response_types": self.auth_method.split(" "),
                    "scope": self.scope.split(" "),
                },
                "add_ons": {
                    # Re-activate this once we have implemented support on AAI side
                    # "dpop": {
                    #     "function": "idpyoidc.client.oauth2.add_on.dpop.add_support",
                    #     "kwargs": {
                    #         "signing_algorithms": [
                    #             "ES256",
                    #             "ES512",
                    #         ]
                    #     },
                    # },
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
        self.rph = RPHandler(self.oidc_url, client_configs=self.oidc_conf)

    async def login(self, _: Request) -> web.HTTPSeeOther:
        """Redirect user to AAI login.

        :raises: HTTPInternalServerError if OIDC configuration init failed
        :returns: HTTPSeeOther redirect to AAI
        """
        LOG.debug("Start login")

        # Generate authentication payload
        try:
            # this returns str even though begin mentions a dict
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
        jwt_token = await self._create_jwt_token(session["userinfo"])

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

    async def logout(self, _: Request) -> web.HTTPSeeOther:
        """Log the user out by clearing cookie.

        :returns: HTTPSeeOther redirect to login page
        """
        response = web.HTTPSeeOther(f"{self.redirect}/")
        response.del_cookie("access_token", path="/")
        response.headers["Location"] = "/" if self.redirect == self.domain else f"{self.redirect}/"
        LOG.debug("Logged out user.")
        return response

    async def _create_jwt_token(self, userinfo: dict[str, Any]) -> str:
        """
        Parse user identity information from the /userinfo response.

        :param userinfo: Dictionary containing user profile claims from the AAI /userinfo endpoint.
        :returns: The JET token.
        :raises HTTPUnauthorized: If the required user ID claims is not found.
        """
        # Extract user ID.
        if "CSCUserName" in userinfo:
            user_id = userinfo["CSCUserName"]
        elif "remoteUserIdentifier" in userinfo:
            user_id = userinfo["remoteUserIdentifier"]
        elif "sub" in userinfo:
            user_id = userinfo["sub"]
        else:
            reason = "Authenticated user is missing required claims."
            LOG.error(reason)
            raise web.HTTPUnauthorized(reason="reason")

        # Extract user name, fallback to user_id if not available.
        given_name = userinfo.get("given_name", "").strip()
        family_name = userinfo.get("family_name", "").strip()

        if given_name or family_name:
            user_name = f"{given_name} {family_name}".strip()
        else:
            user_name = user_id

        return AccessService.create_jwt_token(user_id, user_name)


class AAIServiceHandler(ServiceHandler):
    """AAI handler for API Calls."""

    def __init__(self, headers: Optional[dict[str, Any]] = None) -> None:
        """Get AAI credentials from config."""
        super().__init__(
            base_url=URL(aai_config["oidc_url"].rstrip("/")),
            http_client_headers=headers,
        )

    async def _healthcheck(self) -> dict[str, str]:
        """Check AAI service heartbeat.

        This will return a JSON with well-known OIDC endpoints.

        :returns: Dict with status of the datacite status
        """

        try:
            start = time.time()
            async with self._client.request(
                method="GET",
                url=f"{self.base_url}/.well-known/openid-configuration",
                timeout=ClientTimeout(total=10),
            ) as response:
                content = await response.json()
                LOG.debug("AAI REST API response content is: %r.", content)
                if response.status == 200 and "userinfo_endpoint" in content:
                    status = "Ok" if (time.time() - start) < 1000 else "Degraded"
                else:
                    status = "Down"

                return {"status": status}
        except ClientConnectorError as e:
            LOG.exception("AAI REST API is down with error: %r.", e)
            return {"status": "Down"}
        except InvalidURL as e:
            LOG.exception("AAI REST API status retrieval failed with: %r.", e)
            return {"status": "Error"}
        except web.HTTPError as e:
            LOG.exception("AAI REST API status retrieval failed with: %r.", e)
            return {"status": "Error"}
