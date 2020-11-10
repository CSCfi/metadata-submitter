"""Handle Access for request and OIDC workflow."""

import secrets
import urllib.parse
import hashlib
import json

from aiohttp import web, BasicAuth, ClientSession
from aiohttp.web import Request, Response
from .middlewares import generate_cookie
from authlib.jose import jwt
from authlib.jose.errors import MissingClaimError, InvalidClaimError, ExpiredTokenError, InvalidTokenError, DecodeError

from typing import Dict

from ..helpers.logger import LOG


class AccessHandler:
    """Handler for user access methods."""

    def __init__(self, aai: Dict) -> None:
        """Define AAI variables and paths."""
        self.domain = aai["domain"]
        self.client_id = aai["client_id"]
        self.client_secret = aai["client_secret"]
        self.callback_url = aai["callback_url"]
        self.auth_url = aai["auth_url"]
        self.token_url = aai["token_url"]
        self.revoke_url = aai["revoke_url"]
        self.scope = aai["scope"]
        self.jwk = aai["jwk_server"]
        self.iss = aai["iss"]
        self.nonce = secrets.token_hex()

    async def login(self, req: Request) -> Response:
        """Redirect user to AAI login.

        :param req: GET request
        :raises: 303 redirect
        """
        # Generate a state for callback and save it to session storage
        state = secrets.token_hex()
        await self._save_to_session(req, key="oidc_state", value=state)
        LOG.debug("Start login")
        # Parameters for authorisation request
        params = {
            "client_id": self.client_id,
            "response_type": "code",
            "state": state,
            "redirect_uri": self.callback_url,
            "scope": self.scope,
            "nonce": self.nonce,
        }

        # Prepare response
        url = f"{self.auth_url}?{urllib.parse.urlencode(params)}"
        response = web.HTTPSeeOther(url)
        raise response

    async def callback(self, req: Request) -> Response:
        """Include correct tokens in cookies as a callback after login.

        :param req: GET request
        :raises: 303 redirect
        """
        # Response from AAI must have the query params `state` and `code`
        if "state" in req.query and "code" in req.query:
            LOG.debug("AAI response contained the correct params.")
            params = {"state": req.query["state"], "code": req.query["code"]}
        else:
            reason = f"AAI response is missing mandatory params, received: {req.query}"
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)

        # Verify, that states match
        state = await self._get_from_session(req, "oidc_state")
        if not secrets.compare_digest(str(state), str(params["state"])):
            raise web.HTTPForbidden(reason="Bad user session.")

        auth = BasicAuth(login=self.client_id, password=self.client_secret)
        data = {"grant_type": "authorization_code", "code": params["code"], "redirect_uri": self.callback_url}

        # Set up client authentication for request
        async with ClientSession(auth=auth) as sess:
            # Send request to AAI
            async with sess.post(f"{self.token_url}", data=data) as resp:
                LOG.debug(f"AAI response status: {resp.status}.")
                # Validate response from AAI
                if resp.status == 200:
                    result = await resp.json()
                    if all(x in result for x in ["id_token", "access_token"]):
                        LOG.debug("Both ID and Access tokens received.")
                        access_token = result["access_token"]
                        id_token = result["id_token"]
                        await self._validate_jwt(id_token)
                    else:
                        reason = "AAI response did not contain access and id tokens."
                        LOG.error(reason)
                        raise web.HTTPBadRequest(reason=reason)
                else:
                    reason = f"Token request to AAI failed: {resp}"
                    LOG.error(reason)
                    raise web.HTTPBadRequest(reason=reason)

        await self._save_to_session(req, key="access_token", value=access_token)
        await self._save_to_session(req, key="id_token", value=id_token)

        response = web.HTTPSeeOther(f"{self.domain}/home")

        cookie, _ = generate_cookie(req)

        cookie["referer"] = req.url.host
        cookie["signature"] = (
            hashlib.sha256((cookie["id"] + cookie["referer"] + req.app["Salt"]).encode("utf-8"))
        ).hexdigest()

        session = cookie["id"]

        cookie_crypted = req.app["Crypt"].encrypt(json.dumps(cookie).encode("utf-8")).decode("utf-8")

        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-Cache"
        response.headers["Expires"] = "0"

        response.set_cookie(
            name="MTD_SESSION",
            value=cookie_crypted,
            max_age=3600,
            # secure=trust,  # type: ignore
            # httponly=False,  # type: ignore
        )

        req.app["Cookies"].add(session)

        response.headers["Location"] = "/home"

        LOG.debug(f"cookie MTD_SESSION set {cookie_crypted}")
        return response

    async def logout(self, req: Request) -> Response:
        """Log the user out by revoking tokens.

        :param req: GET request
        :raises: 303 redirect
        """
        # Revoke token at AAI
        access_token = self._get_from_session(req, "access_token")
        auth = BasicAuth(login=self.client_id, password=self.client_secret)
        params = {"token": access_token}
        # Set up client authentication for request
        async with ClientSession(auth=auth) as session:
            async with session.get(f"{self.revoke_url}?{urllib.parse.urlencode(params)}") as resp:
                LOG.debug(f"AAI response status: {resp.status}.")
                # Validate response from AAI
                if resp.status != 200:
                    LOG.error(f"Logout failed at AAI: {resp}.")
                    LOG.error(await resp.json())
                    raise web.HTTPBadRequest(reason=f"Logout failed at AAI: {resp.status}.")

        # Overwrite status cookies with instantly expiring ones
        response = web.HTTPSeeOther(f"{req.url}")
        # response.set_cookie("logged_in", "False", max_age=0, httponly=False)  # type: ignore
        req.app["Session"]["access_token"] = None
        req.app["Session"]["id_token"] = None
        req.app["Session"] = {}

        raise response

    async def _get_key(self) -> dict:
        """Get OAuth2 public key and transform it to usable pem key."""
        try:
            async with ClientSession() as session:
                async with session.get(self.jwk) as r:
                    # This can be a single key or a list of JWK
                    return await r.json()
        except Exception:
            raise web.HTTPUnauthorized(reason="JWK cannot be retrieved")

    async def _validate_jwt(self, token: str) -> None:
        """."""
        key = await self._get_key()  # JWK used to decode token with
        claims_options = {
            "iss": {
                "essential": True,
                "values": self.iss,
            },
            "aud": {"essential": True, "value": self.client_id},
            "exp": {"essential": True},
            "iat": {"essential": True},
            "auth_time": {"essential": True},
            "acr": {
                "essential": True,
                "value": f"{self.iss}/LoginHaka",
            },
            "nonce": {"essential": True, "value": self.nonce},
        }
        try:
            LOG.debug("Validate ID Token")
            decoded_data = jwt.decode(token, key, claims_options=claims_options)  # decode the token
            decoded_data.validate()  # validate the token contents
        # Testing the exceptions is done in integration tests
        except MissingClaimError as e:
            raise web.HTTPUnauthorized(reason=f"Missing claim(s): {e}")
        except ExpiredTokenError as e:
            raise web.HTTPUnauthorized(reason=f"Expired signature: {e}")
        except InvalidClaimError as e:
            raise web.HTTPForbidden(reason=f"Token info not corresponding with claim: {e}")
        except InvalidTokenError as e:
            raise web.HTTPUnauthorized(reason=f"Invalid authorization token: {e}")
        except DecodeError as e:
            raise web.HTTPUnauthorized(reason=f"Invalid JWT format: {e}")
        except Exception:
            raise web.HTTPForbidden(reason="No access")

    async def _save_to_session(self, request: Request, key: str = "key", value: str = "value") -> None:
        """Save a given value to a session key."""
        LOG.debug(f"Save a value for {key} to session.")

        session = request.app["Session"]
        session[key] = value

    async def _get_from_session(self, req: Request, key: str) -> str:
        """Get a value from session storage.

        :param req: GET request
        :param key: name of the key to be returned from session storage
        :returns: Specific value from session storage
        """
        try:
            session = req.app["Session"]
            return session[key]
        except KeyError as e:
            reason = f"Session has no value for {key}: {e}."
            LOG.error(reason)
            raise web.HTTPUnauthorized(reason=reason)
        except Exception as e:
            reason = f"Failed to retrieve {key} from session: {e}"
            LOG.error(reason)
            raise web.HTTPInternalServerError(reason=reason)
