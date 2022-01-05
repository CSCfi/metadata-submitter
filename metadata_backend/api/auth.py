"""Handle Access for request and OIDC workflow."""

import secrets
import urllib.parse
import hashlib
import ujson

from aiohttp import web, BasicAuth, ClientSession
from aiohttp.web import Request, Response
from .middlewares import decrypt_cookie, generate_cookie
from authlib.jose import jwt
from authlib.oidc.core import CodeIDToken
from authlib.jose.errors import MissingClaimError, InvalidClaimError, ExpiredTokenError, InvalidTokenError, DecodeError
from multidict import CIMultiDict
from .operators import UserOperator

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
        self.auth_url = aai["auth_url"]
        self.token_url = aai["token_url"]
        self.revoke_url = aai["revoke_url"]
        self.scope = aai["scope"]
        self.jwk = aai["jwk_server"]
        self.iss = aai["iss"]
        self.user_info = aai["user_info"]
        self.nonce = secrets.token_hex()

    async def login(self, req: Request) -> Response:
        """Redirect user to AAI login.

        :param req: A HTTP request instance
        :raises: HTTPSeeOther redirect to login AAI
        """
        # Generate a state for callback and save it to session storage
        state = secrets.token_hex()
        req.app["OIDC_State"].add(state)

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
        response.headers["Location"] = url
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

        # Verify, that state is pending
        if not params["state"] in req.app["OIDC_State"]:
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

        req.app["Session"][session_id] = {"oidc_state": params["state"], "access_token": access_token}
        req.app["Cookies"].add(session_id)
        req.app["OIDC_State"].remove(params["state"])

        await self._set_user(req, session_id, access_token)

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

    async def _set_user(self, req: Request, session_id: str, token: str) -> None:
        """Set user in current session and return user id based on result of create_user.

        :raises: HTTPBadRequest in could not get user info from AAI OIDC
        :param req: A HTTP request instance
        :param token: access token from AAI
        """
        user_data: Tuple[str, str]
        try:
            headers = CIMultiDict({"Authorization": f"Bearer {token}"})
            async with ClientSession(headers=headers) as sess:
                async with sess.get(f"{self.user_info}") as resp:
                    result = await resp.json()
                    if "eppn" in result:
                        user_data = result["eppn"], f"{result['given_name']} {result['family_name']}"
                    elif "sub" in result:
                        user_data = result["sub"], f"{result['given_name']} {result['family_name']}"
                    else:
                        LOG.error("Could not set user, missing claim eppn or sub.")
                        raise web.HTTPBadRequest(reason="Could not set user, missing claim eppn or sub.")
        except Exception as e:
            LOG.error(f"Could not get information from AAI UserInfo endpoint because of: {e}")
            raise web.HTTPBadRequest(reason="Could not get information from AAI UserInfo endpoint.")

        db_client = req.app["db_client"]
        operator = UserOperator(db_client)
        user_id = await operator.create_user(user_data)
        req.app["Session"][session_id]["user_info"] = user_id

    async def _get_key(self) -> dict:
        """Get OAuth2 public key and transform it to usable pem key.

        :raises: HTTPUnauthorized in case JWK could not be retrieved
        :returns: dictionary with JWK (JSON Web Keys)
        """
        try:
            async with ClientSession() as session:
                async with session.get(self.jwk) as r:
                    # This can be a single key or a list of JWK
                    return await r.json()
        except Exception:
            raise web.HTTPUnauthorized(reason="JWK cannot be retrieved")

    async def _validate_jwt(self, token: str) -> None:
        """Validate id token from AAI according to OIDC specs.

        :raises: HTTPUnauthorized in case token is missing claim, has expired signature or invalid
        :raises: HTTPForbidden does not provide access to the token received
        :param token: id token received from AAI
        """
        key = await self._get_key()  # JWK used to decode token with
        claims_options = {
            "iss": {
                "essential": True,
                "values": self.iss,
            },
            "aud": {"essential": True, "value": self.client_id},
            "exp": {"essential": True},
            "iat": {"essential": True},
        }
        claims_params = {
            "auth_time": {"essential": True},
            "acr": {
                "essential": True,
                "values": f"{self.iss}/LoginHaka,{self.iss}/LoginCSC",
            },
            "nonce": self.nonce,
        }
        try:
            LOG.debug("Validate ID Token")

            decoded_data = jwt.decode(
                token, key, claims_options=claims_options, claims_params=claims_params, claims_cls=CodeIDToken
            )  # decode the token
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
