"""OIDC service."""

import asyncio
import hashlib
import threading
import time
import uuid
from base64 import urlsafe_b64encode
from collections.abc import Callable, Mapping
from contextvars import ContextVar
from functools import cache
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx
import jwt
import requests
import ujson
from fastapi import HTTPException
from fastapi.responses import RedirectResponse
from idpyoidc.client.exception import OidcServiceError
from idpyoidc.client.oauth2.stand_alone_client import StandAloneClient
from idpyoidc.client.rp_handler import RPHandler
from idpyoidc.exception import OidcMsgError
from idpyoidc.message import oidc
from jwt import decode as jwt_decode
from starlette import status
from yarl import URL

from ..api.services.auth import JWT_EXPIRATION, AuthService
from ..conf.oidc import oidc_config
from ..helpers.logger import LOG
from .service_handler import ServiceHandler


class AuthServiceHandler(ServiceHandler):
    """OIDC service."""

    # Seconds to wait on each connect and read from the OIDC provider. Matches cryptojwt's default, set here so
    # that a hung provider cannot hold _setup_lock indefinitely.
    OIDC_REQUEST_TIMEOUT = 10
    # Seconds a login waits for another login to set up the OIDC client before it fails (see _setup_client)
    OIDC_SETUP_WAIT = 30
    # Seconds an unfinished login keeps its state, after which a later login removes it (see begin_login)
    OIDC_LOGIN_TIMEOUT = 600

    def __init__(self) -> None:
        """OIDC service."""

        self._config = oidc_config()

        super().__init__(
            service_name="auth",
            base_url=URL(self._config.OIDC_URL.rstrip("/")),
            healthcheck_url=URL(self._config.OIDC_URL) / ".well-known" / "openid-configuration",
            healthcheck_callback=self.healthcheck_callback,
        )

        self.callback_url = self._config.callback_url
        self.redirect_url = self._config.OIDC_REDIRECT_URL
        self.client_id = self._config.OIDC_CLIENT_ID
        self.client_secret = self._config.OIDC_CLIENT_SECRET.get_secret_value()
        self.oidc_url = self._config.OIDC_URL.rstrip("/") + "/.well-known/openid-configuration"
        self.iss = self._config.OIDC_URL
        self.scope = self._config.OIDC_SCOPE
        self._rph: RPHandler | None = None
        # The OIDC client, set up once by the first login.
        self._oidc_client: StandAloneClient | None = None
        # The _setup_lock prevents multiple logins from setting up _oidc_client at the same time (see _setup_client).
        self._setup_lock = threading.Lock()
        # The time when each login started, oldest first. Used to remove logins that never reach callback(), for example
        # because the user gave up or started a second login, or because the provider refused the login and redirected
        # back without a code. The login is removed once it is older than OIDC_LOGIN_TIMEOUT. Used on the event loop, so
        # no lock is required (see begin_login).
        self._login_started: dict[str, float] = {}
        self._provider_info: dict[str, Any] | None = None

        LOG.info("Using OIDC issuer: %s", self.iss)

        if not self._config.OIDC_VERIFY_ID_TOKEN:
            # Disable ID Token verification during testing.
            oidc.verify_id_token = lambda _self, **_: jwt_decode(
                _self.to_dict().get("id_token", ""), options={"verify_signature": False}, algorithms=["none"]
            )

        # RFC 9449 DPoP support
        self.use_dpop = self._config.OIDC_DPOP

    @property
    def rph(self) -> RPHandler:
        if self._rph is None:
            # With DPoP, idpyoidc sends its requests through dpop_request(), which adds the proofs of the
            # login in progress. The RPHandler and its client are shared by every login.
            self._rph = RPHandler(
                self.oidc_url,
                client_configs=self.get_client_configs(),
                httpc=dpop_request if self.use_dpop else None,
                httpc_params={"verify": True, "timeout": self.OIDC_REQUEST_TIMEOUT},
            )
        return self._rph

    def get_client_configs(self) -> dict[str, dict[str, Any]]:
        """Create OIDC client configuration.

        :return: The OIDC client configuration.
        """
        return {
            "aai": {
                "issuer": self.iss,
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "client_type": "oidc",
                "redirect_uris": [self.callback_url],
                "preference": {
                    "response_types_supported": ["code"],
                    "scopes_supported": self.scope.split(" "),
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
            },
        }

    async def begin_login(self) -> str:
        """Begin an OIDC login and get its authorization URL.

        All logins share one idpyoidc client, which holds the state of every login in progress.
        - The first login sets up the client (see _setup_client).
        - Every login then adds its own state to the client.

        RPHandler.begin("aai") is not used because it would set up a new client for every login, and so
        lose the state of the logins in progress.

        idpyoidc never removes login state itself. The callback removes the state of its login, and each
        login removes the state of logins older than OIDC_LOGIN_TIMEOUT, in case they were never finished.

        This assumes the server runs as a single process. idpyoidc keeps login state in memory, so the
        callback of a login must reach the same process that began it. Running several workers or
        replicas would need sticky sessions or a shared state store.

        :returns: The OIDC authorization endpoint URL.
        """
        rph = self.rph
        try:
            # Setting up the client is done in a thread because idpyoidc sends blocking requests (uses `requests`).
            client = self._oidc_client or await asyncio.to_thread(self._setup_client, rph)
            self._remove_expired_logins(rph)
            # Sends no requests with this client's configuration, so can run on the event loop.
            url: str = rph.init_authorization(client=client)
        except Exception as e:
            # This can be caused if config is improperly configured, and
            # idpyoidc is unable to fetch oidc configuration from the given URL
            LOG.exception("OIDC authorization request failed with: %r", e)
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

        # idpyoidc creates the login's state and returns it only in the URL
        self._login_started[URL(url).query["state"]] = time.monotonic()
        return url

    def _remove_expired_logins(self, rph: RPHandler) -> None:
        """Remove the state of logins that began OIDC_LOGIN_TIMEOUT or more seconds ago and never finished.

        :param rph: The RPHandler that holds the login state
        """
        now = time.monotonic()
        expired = [s for s, started in self._login_started.items() if now - started >= self.OIDC_LOGIN_TIMEOUT]
        for state in expired:
            del self._login_started[state]
            rph.clear_session(state)
        if expired:
            LOG.debug("Removed %d unfinished OIDC logins", len(expired))

    def _setup_client(self, rph: RPHandler) -> StandAloneClient:
        """Get the OIDC client, set up by the first login.

        Runs in a thread, as setting up the client fetches the provider's discovery document and keys with
        blocking requests (see begin_login).
        _setup_lock prevents simultaneous setups. A login waits at most OIDC_SETUP_WAIT seconds for another
        to finish the setup. If the setup fails, the next login tries again.

        :param rph: The RPHandler
        :returns: The OIDC client
        :raises TimeoutError: If another login did not finish setting up the client in time
        """
        if self._oidc_client is not None:
            return self._oidc_client
        if not self._setup_lock.acquire(timeout=self.OIDC_SETUP_WAIT):
            raise TimeoutError("Timed out waiting for another login to set up the OIDC client")
        try:
            if self._oidc_client is None:
                self._oidc_client = rph.client_setup("aai")
            return self._oidc_client
        finally:
            self._setup_lock.release()

    async def callback(self, state: str, code: str) -> tuple[str, str, int]:
        """Handle the OIDC callback and return application-specific JWT.

        Taking the login out of _login_started first means that only one callback can finish it, and that
        expiry cannot remove it meanwhile. idpyoidc's state is removed only after finalize returns. Finalize
        writes the tokens into the state, and would create it again if it had already been removed.

        :param state: The OIDC Authorization Code flow `state` parameter.
        :param code: The OIDC Authorization Code flow `code` parameter.
        :returns: Application JWT, OIDC access token, and OIDC token expiration Unix timestamp
        """
        if self._login_started.pop(state, None) is None:
            # Unknown, already used or expired, or being finished by another callback.
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
        try:
            return await self._finish_login(state, code)
        finally:
            self.rph.clear_session(state)

    async def _finish_login(self, state: str, code: str) -> tuple[str, str, int]:
        """Finish an OIDC login and return application-specific JWT.

        This function completes the OpenID Connect (OIDC) authorization code flow with DPoP.
        It exchanges the authorization code for DPoP-bound tokens, retrieves user information
        and creates an application-specific JWT.

        :param state: The OIDC Authorization Code flow `state` parameter.
        :param code: The OIDC Authorization Code flow `code` parameter.
        :returns: Application JWT, OIDC access token, and OIDC token expiration Unix timestamp
        """

        # The login's state exists, as the callback has claimed the login.
        session_info = self.rph.get_session_information(state)

        # Place authorization_code to session for finalize step
        session_info["code"] = code

        # Each login has its own DPoP handler, and so its own nonce, for RPHandler.finalize()
        try:
            dpop = self._login_dpop_handler(state) if self.use_dpop else None
        except ValueError as e:
            LOG.exception("OIDC DPoP setup failed with: %r", e)
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
        login_dpop = _login_dpop.set(dpop)

        try:
            # finalize exchanges the code for tokens and requests userinfo, in a thread so as not to block the
            # event loop. The thread copies this context, so the login's DPoP handler applies, and it retries
            # nonce errors. Never retry finalize itself: the code may already be redeemed.
            session = await asyncio.to_thread(self.rph.finalize, self.iss, session_info)
        except KeyError as e:
            LOG.exception("Issuer: %s not found, failed with: %r.", session_info["iss"], e)
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
        except (OidcMsgError, OidcServiceError) as e:
            # This exception is raised if RPHandler encounters other errors with OIDC flow:
            LOG.exception("OIDC Callback failed with: %r", e)
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
        finally:
            _login_dpop.reset(login_dpop)

        # Generate a JWT token for application authentication
        jwt_token = await AuthService.create_jwt_token_from_userinfo(session["userinfo"])

        # Get OIDC access token and expiration time
        try:
            access_token, exp_time = self.rph.get_valid_access_token(state)
        except OidcServiceError:
            # Raised if the provider returned no access token, or one that has already expired
            LOG.exception("OIDC provider returned no valid access token")
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

        return jwt_token, access_token, exp_time

    def _login_dpop_handler(self, state: str) -> DPoPHandler:
        """Create the DPoP handler of one OIDC login.

        The endpoints are those the client discovered from the provider. The client exists once
        RPHandler.get_session_information() has found the login's state.

        :param state: The OIDC Authorization Code flow `state` parameter.
        :returns: DPoP handler for the token and userinfo endpoints of the login's provider
        :raises ValueError: If the provider has no token or userinfo endpoint, or the key is invalid
        """
        return DPoPHandler.from_provider_info(self.rph.get_client_from_session_key(state).get_context().provider_info)

    async def initiate_web_session(
        self, jwt_token: str, oidc_access_token: str, oidc_exp_time: int
    ) -> RedirectResponse:
        """Initiate web session by setting JWT token in secure cookie.

        :param jwt_token: The JWT token to be set in the cookie
        :param oidc_access_token: OIDC access token to be stored in separate cookie
        :param oidc_exp_time: OIDC access token expiration Unix timestamp
        :return: HTTPSeeOther redirect to the home page
        """
        LOG.info("OIDC redirect to %r", self.redirect_url)

        response = RedirectResponse(url=self.redirect_url, status_code=status.HTTP_303_SEE_OTHER)

        secure_cookie = self._config.OIDC_SECURE_COOKIE

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
        oidc_max_age = (
            int(max(0, oidc_exp_time - time.time())) if oidc_exp_time > 0 else int(JWT_EXPIRATION.total_seconds())
        )
        response.set_cookie(
            key="oidc_access_token",
            value=oidc_access_token,
            httponly=True,
            secure=secure_cookie,
            samesite="strict",
            path="/",
            max_age=oidc_max_age,
        )
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response

    async def logout(self) -> RedirectResponse:
        """Logout the user by clearing all cookies.

        :returns: Redirect response to login page.
        """
        parsed = urlsplit(self.redirect_url)
        logout_redirect_url = f"{parsed.scheme}://{parsed.netloc}"
        response = RedirectResponse(url=logout_redirect_url, status_code=status.HTTP_303_SEE_OTHER)

        # Delete cookies
        response.delete_cookie("access_token", path="/")
        response.delete_cookie("oidc_access_token", path="/")

        LOG.debug("Logged out user and cleared all cookies.")
        return response

    async def _get_provider_info(self) -> dict[str, Any]:
        """Get the OIDC provider's discovery document, fetched once per handler.

        A failed fetch is not kept, so the next call fetches the document again.

        :returns: The provider's metadata from its discovery document
        :raises ValueError: If the discovery document is not a JSON object
        """
        if self._provider_info is None:
            provider_info = await self._request(url=URL(self.oidc_url))
            if not isinstance(provider_info, dict):
                raise ValueError(f"OIDC discovery document from {self.oidc_url} is not a JSON object")
            self._provider_info = provider_info
        return self._provider_info

    async def get_pouta_access_token_from_userinfo(self, oidc_access_token: str) -> str:
        """Fetch pouta_access_token from OIDC userinfo endpoint.

        :param oidc_access_token: OIDC access token.
        :returns: pouta_access_token from userinfo response.
        """
        try:
            if not oidc_access_token:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing OIDC access token")

            # The userinfo endpoint is the one the provider lists in its discovery document
            provider_info = await self._get_provider_info()
            headers = {"Authorization": f"Bearer {oidc_access_token}"}
            send: Callable[..., requests.Response]
            if self.use_dpop:
                # As for the login's userinfo request: adds the proof, changes the scheme to DPoP and retries a
                # nonce error
                send = DPoPHandler.from_provider_info(provider_info).request
            else:
                send = requests.request
            # requests blocks, so the request runs in a thread
            response = await asyncio.to_thread(
                send, "GET", provider_info["userinfo_endpoint"], headers=headers, timeout=self.OIDC_REQUEST_TIMEOUT
            )
            response.raise_for_status()
            return str(response.json().get("pouta_access_token", ""))
        except HTTPException:
            raise
        except Exception as e:
            LOG.exception("Failed to retrieve pouta access token from userinfo: %r", e)
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    @staticmethod
    async def healthcheck_callback(response: httpx.Response) -> bool:
        return "userinfo_endpoint" in response.json()


@cache
def _load_private_jwk(path: Path) -> tuple[dict[str, Any], Any]:
    """Load the private DPoP key, once per process.

    The key is never reloaded, so a rotated key is used only after a restart. A failed load is not
    cached, so a fixed key file is used on the next call.

    :param path: Path of the private JWKS file
    :returns: Raw key data of the first key and its cryptography key object
    :raises ValueError: If key file or its parameters are invalid
    """
    # Load JWKS file
    try:
        with open(path) as f:
            jwks: dict[str, Any] = ujson.load(f)
    except (OSError, ValueError) as e:
        raise ValueError(f"Failed to load private JWKS from {path}: {e}") from e

    if not jwks.get("keys"):
        raise ValueError(f"No keys found in JWKS file: {path}")

    private_key_data: dict[str, Any] = jwks["keys"][0]

    # Validate key type
    if private_key_data.get("kty") != "EC":
        raise ValueError(f"Key must be EC type, got: {private_key_data.get('kty')}")
    # Proofs are signed with ES256, which needs a P-256 key
    if private_key_data.get("crv") != "P-256":
        raise ValueError(f"Key must be on curve P-256 for ES256, got: {private_key_data.get('crv')}")
    if "d" not in private_key_data:
        raise ValueError("Key must contain private parameter 'd' for signing")

    # Use PyJWT's PyJWK to convert JWK to cryptography key object
    try:
        return private_key_data, jwt.PyJWK(private_key_data).key
    except jwt.PyJWTError as e:
        raise ValueError(f"Invalid private key in JWKS file {path}: {e}") from e


class DPoPHandler:
    """RFC 9449 Demonstrating Proof of Possession (DPoP) handler.

    Generates and manages DPoP proofs for OIDC authentication since
    idpyoidc library does not support it correctly out-of-the-box.
    """

    PRIVATE_JWK_PATH = Path(__file__).parent.parent.parent / "private" / "private_jwks.json"

    def __init__(self, *, token_endpoint: str, userinfo_endpoint: str) -> None:
        """Initialize DPoP handler with private key.

        :param token_endpoint: Token endpoint whose requests request() sends with DPoP proofs
        :param userinfo_endpoint: Userinfo endpoint whose requests request() sends with DPoP proofs
        :raises ValueError: If an endpoint is missing, or key file or its parameters are invalid
        """
        missing = [name for name, url in (("token", token_endpoint), ("userinfo", userinfo_endpoint)) if not url]
        if missing:
            raise ValueError(f"OIDC provider has no {' or '.join(missing)} endpoint for DPoP")

        self.nonce: str | None = None
        self.token_endpoint = token_endpoint
        self.userinfo_endpoint = userinfo_endpoint

        # Store raw key data for public JWK extraction
        self.private_key_data, self.private_key = _load_private_jwk(self.PRIVATE_JWK_PATH)
        self.public_jwk = self._extract_public_jwk()

    @classmethod
    def from_provider_info(cls, provider_info: Mapping[str, Any]) -> "DPoPHandler":
        """Create a DPoP handler for the endpoints in an OIDC provider's metadata.

        :param provider_info: The provider's metadata, from its discovery document
        :returns: DPoP handler for the provider's token and userinfo endpoints
        :raises ValueError: If an endpoint is missing, or key file or its parameters are invalid
        """
        return cls(
            token_endpoint=provider_info.get("token_endpoint", ""),
            userinfo_endpoint=provider_info.get("userinfo_endpoint", ""),
        )

    def _extract_public_jwk(self) -> dict[str, Any]:
        """Extract public JWK (without private parameter) for proof header.

        :returns: Public JWK object
        """
        return {
            "kty": self.private_key_data["kty"],
            "crv": self.private_key_data["crv"],
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

    def request(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        """Send a request of the OIDC login with DPoP headers.

        For RFC 9449 DPoP compliance:
        - Token endpoint: Add DPoP proof header
        - Userinfo endpoint: Add DPoP proof + change Authorization to "DPoP"

        Requests to any other URL, such as for the provider's keys, are sent unchanged.

        A request the provider rejects for want of its nonce (RFC 9449 Section 8 and 9) is sent once
        more with a proof that has the nonce. The provider has not acted on the rejected request, so a
        token request does not redeem its code twice.

        :param method: HTTP method (GET, POST, etc.)
        :param url: Request URL
        :param kwargs: Additional request arguments
        :returns: HTTP response
        """
        if url not in (self.token_endpoint, self.userinfo_endpoint):
            return requests.request(method, url, **kwargs)

        headers = kwargs["headers"] = dict(kwargs.get("headers") or {})

        # Userinfo endpoint: bind the proof to the access token (ath claim) and change the scheme to DPoP.
        # Token endpoint: a proof without access token binding.
        access_token = None
        if url == self.userinfo_endpoint:
            auth_header = headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                access_token = auth_header[7:]  # Remove "Bearer " prefix
                headers["Authorization"] = f"DPoP {access_token}"
                LOG.debug("Changed Authorization scheme from Bearer to DPoP for %s", url)

        headers["DPoP"] = self.generate_proof(method, url, access_token=access_token)
        LOG.debug("Added DPoP proof to %s %s", method, url)
        response = requests.request(method, url, **kwargs)

        # Extract nonce from DPoP-Nonce response header for next request (RFC 9449 Section 8)
        nonce = response.headers.get("DPoP-Nonce")
        if nonce and nonce != self.nonce and self._is_nonce_error(response):
            LOG.debug("DPoP nonce required by %s %s, retrying with server nonce", method, url)
            self.update_nonce(nonce)
            kwargs["headers"] = {**headers, "DPoP": self.generate_proof(method, url, access_token=access_token)}
            response = requests.request(method, url, **kwargs)
            nonce = response.headers.get("DPoP-Nonce")
        self.update_nonce(nonce)

        return response

    @staticmethod
    def _is_nonce_error(response: requests.Response) -> bool:
        """Tell whether the provider rejected a request because its DPoP proof lacked the nonce.

        The token endpoint returns error `use_dpop_nonce` in a 400 response body (RFC 9449 Section 8),
        the userinfo endpoint in the WWW-Authenticate header of a 401 response (Section 9).

        :param response: HTTP response
        :returns: True if the request should be sent again with the nonce
        """
        if response.status_code not in (400, 401):
            return False
        if "use_dpop_nonce" in response.headers.get("WWW-Authenticate", ""):
            return True
        try:
            body = response.json()
        except ValueError:
            return False
        return isinstance(body, dict) and body.get("error") == "use_dpop_nonce"


# The DPoP handler of the OIDC login in progress in this context.
_login_dpop: ContextVar[DPoPHandler | None] = ContextVar("login_dpop", default=None)


def dpop_request(method: str, url: str, **kwargs: Any) -> requests.Response:
    """Send an idpyoidc request, with DPoP headers if an OIDC login is in progress.

    idpyoidc's client calls this in place of requests.request().

    :param method: HTTP method (GET, POST, etc.)
    :param url: Request URL
    :param kwargs: Additional request arguments
    :returns: HTTP response
    """
    dpop = _login_dpop.get()
    if dpop is None:
        return requests.request(method, url, **kwargs)
    return dpop.request(method, url, **kwargs)
