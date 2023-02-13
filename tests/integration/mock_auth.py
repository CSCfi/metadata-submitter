"""Mock OAUTH2 aiohttp.web server."""

import logging
import urllib
from os import getenv
from time import time
from typing import Tuple

from aiohttp import web
from authlib.jose import RSAKey, jwt

FORMAT = "[%(asctime)s][%(levelname)-8s](L:%(lineno)s) %(funcName)s: %(message)s"
logging.basicConfig(format=FORMAT, datefmt="%Y-%m-%d %H:%M:%S")

LOG = logging.getLogger("server")
LOG.setLevel(getenv("LOG_LEVEL", "INFO"))


def generate_token() -> Tuple:
    """Generate RSA Key pair to be used to sign token and the JWT Token itself."""
    key = RSAKey.generate_key(is_private=True)
    # we set no `exp` and other claims as they are optional in a real scenario these should bde set
    # See available claims here: https://www.iana.org/assignments/jwt/jwt.xhtml
    # the important claim is the "authorities"
    public_jwk = key.as_dict(is_private=False)
    private_jwk = dict(key)

    return (public_jwk, private_jwk)


# oidcrp is strict about iat, exp, ttl, so we can't hard code them
iat = int(time())
ttl = 3600
exp = iat + ttl

nonce = "nonce"
jwk_pair = generate_token()

user_sub = "test@test.example"
user_given_name = "User"
user_family_name = "test"

mock_auth_url_docker = getenv("OIDC_URL", "http://mockauth:8000")  # called from inside docker-network
mock_auth_url_local = getenv("OIDC_URL_TEST", "http://localhost:8000")  # called from local machine

header = {
    "jku": f"{mock_auth_url_docker}/jwk",
    "kid": "rsa1",
    "alg": "RS256",
    "typ": "JWT",
}


async def setmock(req: web.Request) -> web.Response:
    """Auth endpoint."""
    global user_sub, user_family_name, user_given_name
    user_sub = req.query["sub"]
    user_family_name = req.query["family"]
    user_given_name = req.query["given"]
    LOG.info(f"{mock_auth_url_local}: {user_sub}, {user_family_name}, {user_given_name}")

    return web.HTTPOk()


async def auth(req: web.Request) -> web.Response:
    """Auth endpoint."""
    params = {
        "state": req.query["state"],
        "code": "code",
    }
    global nonce, user_family_name, user_given_name
    nonce = req.query["nonce"]
    callback_url = req.query["redirect_uri"]
    url = f"{callback_url}?{urllib.parse.urlencode(params)}"

    LOG.info(url)

    response = web.HTTPSeeOther(url)
    return response


async def token(req: web.Request) -> web.Response:
    """Auth endpoint."""
    global nonce, user_sub, user_family_name, user_given_name
    # oidcrp is strict about iat, exp, ttl, so we can't hard code them
    iat = int(time())
    ttl = 3600
    exp = iat + ttl
    id_token = {
        "at_hash": "fSi3VUa5i2o2SgY5gPJZgg",
        "eduPersonAffiliation": "member;staff",
        "sub": user_sub,
        "displayName": f"{user_given_name} {user_family_name}",
        "iss": mock_auth_url_docker,
        "schacHomeOrganizationType": "urn:schac:homeOrganizationType:test:other",
        "given_name": user_given_name,
        "nonce": nonce,
        "aud": "aud2",
        "acr": f"{mock_auth_url_docker}/LoginHaka",
        "nsAccountLock": "false",
        "eduPersonScopedAffiliation": "staff@test.what;member@test.what",
        "auth_time": iat,
        "name": f"{user_given_name} {user_family_name}",
        "schacHomeOrganization": "test.what",
        "exp": exp,
        "iat": iat,
        "family_name": user_family_name,
        "email": user_sub,
    }
    data = {
        "access_token": "test",
        "id_token": jwt.encode(header, id_token, jwk_pair[1]).decode("utf-8"),
        "token_type": "Bearer",
        "expires_in": ttl,
    }

    LOG.info(data)

    return web.json_response(data)


async def jwk_response(request: web.Request) -> web.Response:
    """Mock JSON Web Key server."""
    keys = [jwk_pair[0]]
    keys[0]["kid"] = "rsa1"
    data = {"keys": keys}

    LOG.info(data)

    return web.json_response(data)


async def userinfo(request: web.Request) -> web.Response:
    """Mock an authentication to ELIXIR AAI for GA4GH claims."""
    global nonce, user_sub, user_family_name, user_given_name
    user_info = {
        "eduPersonAffiliation": "member;staff",
        "sub": user_sub,
        "displayName": f"{user_given_name} {user_family_name}",
        "schacHomeOrganizationType": "urn:schac:homeOrganizationType:test:other",
        "given_name": user_given_name,
        "uid": user_sub,
        "nsAccountLock": "false",
        "eduPersonScopedAffiliation": "staff@test.what;member@test.what",
        "name": f"{user_given_name} {user_family_name}",
        "schacHomeOrganization": "test.what",
        "family_name": user_family_name,
        "email": user_sub,
        "sdSubmitProjects": "1000 2000 3000",
        "eduperson_entitlement": [
            "test_namespace:test_root:group1#client",
            "test_namespace:test_root:group2#client",
            "test_namespace:test_root:group3#client",
        ],
    }

    LOG.info(user_info)

    return web.json_response(user_info)


async def oidc_config(request: web.Request) -> web.Response:
    """Return standard OIDC configuration."""
    oidc_config_json = {
        "issuer": mock_auth_url_docker,
        "authorization_endpoint": f"{mock_auth_url_local}/authorize",
        "token_endpoint": f"{mock_auth_url_docker}/token",
        "userinfo_endpoint": f"{mock_auth_url_docker}/userinfo",
        "jwks_uri": f"{mock_auth_url_docker}/keyset",
        "response_types_supported": [
            "code",
            "id_token",
            "token id_token",
            "code id_token",
            "code token",
            "code token id_token",
        ],
        "subject_types_supported": ["public", "pairwise"],
        "grant_types_supported": [
            "authorization_code",
            "implicit",
            "refresh_token",
            "urn:ietf:params:oauth:grant-type:device_code",
        ],
        "id_token_encryption_alg_values_supported": [
            "RSA1_5",
            "RSA-OAEP",
            "RSA-OAEP-256",
            "A128KW",
            "A192KW",
            "A256KW",
            "A128GCMKW",
            "A192GCMKW",
            "A256GCMKW",
        ],
        "id_token_encryption_enc_values_supported": ["A128CBC-HS256"],
        "id_token_signing_alg_values_supported": [
            "RS256",
            "RS384",
            "RS512",
            "HS256",
            "HS384",
            "HS512",
            "ES256",
        ],
        "userinfo_encryption_alg_values_supported": [
            "RSA1_5",
            "RSA-OAEP",
            "RSA-OAEP-256",
            "A128KW",
            "A192KW",
            "A256KW",
            "A128GCMKW",
            "A192GCMKW",
            "A256GCMKW",
        ],
        "userinfo_encryption_enc_values_supported": ["A128CBC-HS256"],
        "userinfo_signing_alg_values_supported": [
            "RS256",
            "RS384",
            "RS512",
            "HS256",
            "HS384",
            "HS512",
            "ES256",
        ],
        "dpop_signing_alg_values_supported": [
            "none",
            "RS256",
            "RS384",
            "RS512",
            "HS256",
            "HS384",
            "HS512",
            "ES256",
            "ES384",
            "ES512",
        ],
        "request_object_signing_alg_values_supported": [
            "none",
            "RS256",
            "RS384",
            "RS512",
            "HS256",
            "HS384",
            "HS512",
            "ES256",
            "ES384",
            "ES512",
        ],
        "token_endpoint_auth_methods_supported": [
            "client_secret_basic",
            "client_secret_post",
            "client_secret_jwt",
            "private_key_jwt",
        ],
        "claims_parameter_supported": True,
        "request_parameter_supported": True,
        "request_uri_parameter_supported": False,
        "require_request_uri_registration": False,
        "display_values_supported": ["page"],
        "scopes_supported": ["openid"],
        "response_modes_supported": ["query", "fragment", "form_post"],
        "claims_supported": [
            "aud",
            "iss",
            "sub",
            "iat",
            "exp",
            "acr",
            "auth_time",
            "ga4gh_passport_v1",
            "remoteUserIdentifier",
        ],
    }
    return web.json_response(oidc_config_json)


async def init() -> web.Application:
    """Start server."""
    app = web.Application()
    app.router.add_get("/setmock", setmock)
    app.router.add_get("/authorize", auth)
    app.router.add_post("/token", token)
    app.router.add_get("/keyset", jwk_response)
    app.router.add_get("/userinfo", userinfo)
    app.router.add_get("/.well-known/openid-configuration", oidc_config)
    return app


if __name__ == "__main__":
    web.run_app(init(), port=8000)
