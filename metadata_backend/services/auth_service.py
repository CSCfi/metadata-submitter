"""OIDC service."""

import hashlib
import os
import time
import uuid
from base64 import urlsafe_b64encode
from functools import partial
from pathlib import Path
from typing import Any

import httpx
import idpyoidc.message.oidc as oidc
import jwt
import ujson
from fastapi import HTTPException
from fastapi.responses import RedirectResponse
from idpyoidc.client.exception import OidcServiceError
from idpyoidc.client.rp_handler import RPHandler
from idpyoidc.exception import OidcMsgError
from jwt import decode as jwt_decode
from requests import Session
from starlette import status
from yarl import URL

from ..api.services.auth import JWT_EXPIRATION, AuthService
from ..conf.oidc import oidc_config
from ..helpers.logger import LOG
from .service_handler import ServiceHandler

OIDC_PROFILE_WEB = "web"
OIDC_PROFILE_CLI = "cli"


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

        self.callback_web_url = self._config.callback_web_url
        self.callback_cli_url = self._config.callback_cli_url
        self.redirect_url = self._config.OIDC_REDIRECT_URL
        self.client_id = self._config.OIDC_CLIENT_ID
        self.client_secret = self._config.OIDC_CLIENT_SECRET
        self.oidc_url = self._config.OIDC_URL.rstrip("/") + "/.well-known/openid-configuration"
        self.iss = self._config.OIDC_URL
        self.scope = self._config.OIDC_SCOPE
        self.verify_id_token = self._config.OIDC_VERIFY_ID_TOKEN
        self.auth_method = "code"
        self._rph: RPHandler | None = None

        if not self._config.OIDC_VERIFY_ID_TOKEN:
            # Disable ID Token verification during testing.
            oidc.verify_id_token = lambda _self, **_: jwt_decode(
                _self.to_dict().get("id_token", ""), options={"verify_signature": False}, algorithms=["none"]
            )

        # Initialize DPoP handler for RFC 9449 support
        self.use_dpop = self._config.OIDC_DPOP
        self._dpop: DPoPHandler | None = None

    @property
    def dpop(self) -> DPoPHandler | None:
        if self.use_dpop:
            if self._dpop is None:
                self._dpop = DPoPHandler()
            return self._dpop
        else:
            return None

    @property
    def rph(self) -> RPHandler:
        if self._rph is None:
            self._rph = RPHandler(self.oidc_url, client_configs=self.get_client_configs())
        return self._rph

    def _client_config(self, callback_url: str) -> dict[str, Any]:
        """

        Create OIDC client configuration.

        :param callback_url: The callback URL.
        :return: The OIDC client configuration.
        """
        return {
            "issuer": self.iss,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "client_type": "oidc",
            "redirect_uris": [callback_url],
            "behaviour": {
                "response_types": self.auth_method.split(" "),
                "scope": self.scope.split(" "),
            },
            "add_ons": {
                "pkce": {
                    "function": "idpyoidc.client.oauth2.add_on.pkce.add_support",
                    "kwargs": {
                        "code_challenge_length": 64,
                        "code_challenge_method": "S256",
                    },
                },
            },
        }

    def get_client_configs(self) -> dict[str, dict[str, Any]]:
        return {
            OIDC_PROFILE_WEB: self._client_config(self.callback_web_url),
            OIDC_PROFILE_CLI: self._client_config(self.callback_cli_url),
        }

    async def get_oidc_auth_url(self, oidc_profile: str) -> str:
        """
        Get the OIDC authorize URL for the given profile.

        :param oidc_profile: The OIDC profile.
        :returns: The OIDC authorize URL for the given profile.
        """

        # Generate authentication payload
        try:
            authorization_url = self.rph.begin(oidc_profile)
        except Exception as e:
            # This can be caused if config is improperly configured, and
            # idpyoidc is unable to fetch oidc configuration from the given URL
            LOG.exception("OIDC authorization request failed with: %r", e)
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

        # LOG.debug(f"Create OIDC authorization URL: {authorization_url}")

        return str(authorization_url)

    async def callback(self, state: str, code: str) -> tuple[str, dict[str, Any]]:
        """Handle the OIDC callback and return application-specific JWT.

        This function completes the OpenID Connect (OIDC) authorization code flow with DPoP.
        It exchanges the authorization code for DPoP-bound tokens, retrieves user information
        and creates an application-specific JWT.

        :param state: The OIDC Authorization Code flow `state` parameter.
        :param code: The OIDC Authorization Code flow `code` parameter.
        :returns: JWT token as a string and userinfo dictionary
        """

        # Verify oidc_state and retrieve auth session
        try:
            session_info = self.rph.get_session_information(state)
        except KeyError:
            # This exception is raised if the RPHandler doesn't have the supplied "state"
            LOG.exception("OIDC session not initialised")
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

        # Place authorization_code to session for finalize step
        session_info["code"] = code

        # Setup HTTP interception for DPoP before RPHandler.finalize()
        if self.use_dpop:
            self.dpop.setup_http_interception()

        try:
            # finalize requests id_token and access_token with code, validates them and requests userinfo data
            # With DPoP interception enabled, token endpoint requests will include DPoP proofs
            session = self.rph.finalize(self.iss, session_info)
        except KeyError as e:
            LOG.exception("Issuer: %s not found, failed with: %r.", session_info["iss"], e)
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
        except (OidcMsgError, OidcServiceError) as e:
            # Check if this is a "use_dpop_nonce" error
            if self.use_dpop and "use_dpop_nonce" in str(e):
                LOG.debug("Received use_dpop_nonce error, retrying token request with server nonce")
                try:
                    # Remove the failed state from rph to allow retry
                    session_state = self.rph.get_session_information(state)
                    session_state["code"] = code

                    # Retry finalize with fresh session info and new nonce from DPoP-Nonce header
                    session = self.rph.finalize(self.iss, session_state)
                except (OidcMsgError, OidcServiceError) as retry_error:
                    LOG.exception("OIDC Callback failed on retry with: %r", retry_error)
                    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
            else:
                # This exception is raised if RPHandler encounters other errors with OIDC flow:
                LOG.exception("OIDC Callback failed with: %r", e)
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
        finally:
            # Clean up HTTP interception
            if self.use_dpop:
                self.dpop.teardown_http_interception()

        # Generate a JWT token for application authentication
        jwt_token = await AuthService.create_jwt_token_from_userinfo(session["userinfo"])
        return jwt_token, session["userinfo"]

    async def initiate_web_session(self, jwt_token: str, userinfo: dict[str, Any]) -> RedirectResponse:
        """
        Initiate web session by setting JWT token in secure cookie.

        :param jwt_token: The JWT token to be set in the cookie
        :param userinfo: The user information dictionary
        :return: HTTPSeeOther redirect to the home page
        """
        LOG.info("OIDC redirect to %r", f"{self.redirect_url}")

        response = RedirectResponse(url=self.redirect_url, status_code=status.HTTP_303_SEE_OTHER)

        secure_cookie = os.environ.get("OIDC_SECURE_COOKIE", "").upper() != "FALSE"

        # Set the application JWT token
        response.set_cookie(
            key="access_token",
            value=jwt_token,
            httponly=True,
            secure=secure_cookie,
            samesite="strict",
            path="/",
            max_age=int(JWT_EXPIRATION.total_seconds()),
        )
        # TODO(improve): Remove pouta_access_token from session cookies.
        # Instead fetch it from /userinfo whenever needed.
        pouta_access_token = userinfo.get("pouta_access_token", "").strip()
        response.set_cookie(
            key="pouta_access_token",
            value=pouta_access_token,
            httponly=True,
            secure=secure_cookie,
            samesite="strict",
            path="/",
            max_age=int(JWT_EXPIRATION.total_seconds()),
        )
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-Cache"
        response.headers["Expires"] = "0"
        return response

    async def logout(self) -> RedirectResponse:
        """
        Logout the user by clearing all cookies.

        :returns: Redirect response to login page.
        """

        response = RedirectResponse(url=self.redirect_url, status_code=status.HTTP_303_SEE_OTHER)

        # Delete cookies
        response.delete_cookie("access_token", path="/")
        response.delete_cookie("pouta_access_token", path="/")

        LOG.debug("Logged out user and cleared all cookies.")
        return response

    @staticmethod
    async def healthcheck_callback(response: httpx.Response) -> bool:
        return "userinfo_endpoint" in response.json()


class DPoPHandler:
    """RFC 9449 Demonstrating Proof of Possession (DPoP) handler.

    Generates and manages DPoP proofs for OIDC authentication since
    idpyoidc library does not support it correctly out-of-the-box.
    """

    PRIVATE_JWK_PATH = Path(__file__).parent.parent.parent / "private" / "private_jwks.json"

    def __init__(self) -> None:
        """Initialize DPoP handler with private key.

        :raises ValueError: If key file or its parameters are invalid
        """
        self.nonce: str | None = None

        # Load JWKS file
        try:
            with open(self.PRIVATE_JWK_PATH) as f:
                jwks: dict[str, Any] = ujson.load(f)
        except (OSError, ValueError) as e:
            raise ValueError(f"Failed to load private JWKS from {self.PRIVATE_JWK_PATH}: {e}") from e

        if not jwks.get("keys"):
            raise ValueError(f"No keys found in JWKS file: {self.PRIVATE_JWK_PATH}")

        # Store raw key data for public JWK extraction
        self.private_key_data: dict[str, Any] = jwks["keys"][0]

        # Validate key type
        if self.private_key_data.get("kty") != "EC":
            raise ValueError(f"Key must be EC type, got: {self.private_key_data.get('kty')}")
        if "d" not in self.private_key_data:
            raise ValueError("Key must contain private parameter 'd' for signing")

        # Use PyJWT's PyJWK to convert JWK to cryptography key object
        pyjwk = jwt.PyJWK(self.private_key_data)
        self.private_key = pyjwk.key
        self.public_jwk = self._extract_public_jwk()

    def _extract_public_jwk(self) -> dict[str, Any]:
        """Extract public JWK (without private parameter) for proof header.

        :returns: Public JWK object
        """
        return {
            "kty": self.private_key_data["kty"],
            "crv": self.private_key_data.get("crv", "P-256"),
            "x": self.private_key_data["x"],
            "y": self.private_key_data["y"],
            "kid": self.private_key_data.get("kid"),
            "alg": self.private_key_data.get("alg", "ES256"),
        }

    def update_nonce(self, nonce: str | None) -> None:
        """Update DPoP nonce from server response (RFC 9449 Section 8).

        :param nonce: Server-provided nonce (optional)
        """
        if nonce:
            self.nonce = nonce
            LOG.debug("Updated DPoP nonce")

    def generate_proof(self, htm: str, htu: str, access_token: str | None = None) -> str:
        """Generate DPoP proof JWT.

        DPoP proof is a JWT signed with the client's private key, bound to:
        - HTTP method (htm) and URI (htu)
        - Access token hash (ath) if token provided
        - Server nonce if available (for replay protection)

        :param htm: HTTP method (GET, POST, etc.)
        :param htu: HTTP URI (absolute)
        :param access_token: Optional access token to bind proof via ath claim
        :returns: DPoP proof JWT (signed)
        :raises ValueError: If signing fails
        """

        # Unique proof ID and timestamp
        jti = str(uuid.uuid4())
        iat = int(time.time())

        payload = {
            "jti": jti,
            "htm": htm,
            "htu": htu,
            "iat": iat,
            "nonce": self.nonce,
        }

        # Bind proof to access token if provided
        if access_token:
            token_hash = hashlib.sha256(access_token.encode()).digest()
            ath = urlsafe_b64encode(token_hash).decode().rstrip("=")
            payload["ath"] = ath

        # Sign proof with private key
        try:
            proof_jwt = jwt.encode(
                payload,
                self.private_key,
                algorithm="ES256",
                headers={
                    "typ": "dpop+jwt",
                    "alg": "ES256",
                    "jwk": self.public_jwk,
                },
            )
            LOG.debug("Generated DPoP proof for %s %s", htm, htu)
            return proof_jwt
        except Exception as e:
            raise ValueError(f"Failed to sign DPoP proof: {e}") from e

    def setup_http_interception(self) -> None:
        """Patch requests.Session.request to inject DPoP headers before each request."""

        self._original_request = Session.request

        # Reset nonce to None before each authentication attempt
        # Auth server will provide nonce in response for subsequent requests
        self.nonce = None
        LOG.debug("Reset DPoP nonce to None for new authentication attempt")

        # Apply patch using functools.partial to bind self to the instance method
        Session.request = partial(self._patched_request)  # type: ignore[method-assign]

    def _patched_request(
        self,
        session_self: Session,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> Any:
        """Patched request method that injects DPoP header and modifies Authorization scheme.

        For RFC 9449 DPoP compliance:
        - Token endpoint: Add DPoP proof header
        - Protected resources (userinfo, etc): Add DPoP proof + change Authorization to "DPoP"

        :param session_self: The requests.Session instance (when called via partial binding)
        :param method: HTTP method (GET, POST, etc.)
        :param url: Request URL
        :param kwargs: Additional request arguments
        :returns: HTTP response from original request method
        """
        if "headers" not in kwargs:
            kwargs["headers"] = {}

        # Add DPoP proof to token endpoint requests
        if "/token" in url:
            # Generate DPoP proof for token endpoint (without access token binding)
            proof = self.generate_proof(method, url)
            kwargs["headers"]["DPoP"] = proof
            LOG.debug("Added DPoP proof to %s %s", method, url)

        # Add DPoP proof to protected resource requests (userinfo, etc.)
        elif "/userinfo" in url or "Authorization" in kwargs["headers"]:
            # Extract access token from Authorization header if present
            access_token = None
            auth_header = kwargs["headers"].get("Authorization", "")

            if auth_header.startswith("Bearer "):
                # Extract token and change scheme from Bearer to DPoP
                access_token = auth_header[7:]  # Remove "Bearer " prefix
                kwargs["headers"]["Authorization"] = f"DPoP {access_token}"
                LOG.debug("Changed Authorization scheme from Bearer to DPoP for %s", url)

            # Generate DPoP proof with access token binding (ath claim)
            proof = self.generate_proof(method, url, access_token=access_token)
            kwargs["headers"]["DPoP"] = proof
            LOG.debug("Added DPoP proof with token binding to %s %s", method, url)

        # Make the original request
        response = self._original_request(session_self, method, url, **kwargs)

        # Extract nonce from DPoP-Nonce response header for next request (RFC 9449 Section 8)
        if "DPoP-Nonce" in response.headers:
            self.update_nonce(response.headers["DPoP-Nonce"])

        return response

    def teardown_http_interception(self) -> None:
        """Restore original requests.Session.request method."""

        if hasattr(self, "_original_request"):
            Session.request = self._original_request  # type: ignore[method-assign]
            delattr(self, "_original_request")
