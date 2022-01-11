"""Mock OAUTH2 aiohttp.web server."""

from time import time
from aiohttp import web
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend
from authlib.jose import jwt, jwk
from typing import Tuple
import urllib
import logging


def generate_token() -> Tuple:
    """Generate RSA Key pair to be used to sign token and the JWT Token itself."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048, backend=default_backend())
    public_key = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfo
    )
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    # we set no `exp` and other claims as they are optional in a real scenario these should bde set
    # See available claims here: https://www.iana.org/assignments/jwt/jwt.xhtml
    # the important claim is the "authorities"
    public_jwk = jwk.dumps(public_key, kty="RSA")
    private_jwk = jwk.dumps(pem, kty="RSA")

    return (public_jwk, private_jwk)


# oidcrp is strict about iat, exp, ttl, so we can't hard code them
iat = int(time())
ttl = 3600
exp = iat + ttl

nonce = ""
jwk_pair = generate_token()

user_sub = ""
user_given_name = ""
user_family_name = ""

header = {"jku": "http://mockauth:8000/jwk", "kid": "rsa1", "alg": "RS256", "typ": "JWT"}


async def setmock(req: web.Request) -> web.Response:
    """Auth endpoint."""
    global user_sub, user_family_name, user_given_name
    user_sub = req.query["sub"]
    user_family_name = req.query["family"]
    user_given_name = req.query["given"]

    logging.info(user_sub, user_family_name, user_given_name)

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

    logging.info(url)

    response = web.HTTPSeeOther(url)
    return response


async def token(req: web.Request) -> web.Response:
    """Auth endpoint."""
    global nonce, user_sub, user_family_name, user_given_name
    id_token = {
        "at_hash": "fSi3VUa5i2o2SgY5gPJZgg",
        "sub": "smth",
        "eduPersonAffiliation": "member;staff",
        "sub": user_sub,
        "displayName": f"{user_given_name} {user_family_name}",
        "iss": "http://mockauth:8000",
        "schacHomeOrganizationType": "urn:schac:homeOrganizationType:test:other",
        "given_name": user_given_name,
        "nonce": nonce,
        "aud": "aud2",
        "acr": "http://mockauth:8000/LoginHaka",
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

    logging.info(data)

    return web.json_response(data)


async def jwk_response(request: web.Request) -> web.Response:
    """Mock JSON Web Key server."""
    keys = [jwk_pair[0]]
    keys[0]["kid"] = "rsa1"
    data = {"keys": keys}

    logging.info(data)

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
    }

    logging.info(user_info)

    return web.json_response(user_info)


async def oidc_config(request: web.Request) -> web.Response:
    """Return standard OIDC configuration."""
    oidc_config_json = {
        "issuer": "http://mockauth:8000",
        "authorization_endpoint": "http://localhost:8000/authorize",  # must be localhost to be accessible outside of docker-network
        "token_endpoint": "http://mockauth:8000/token",
        "userinfo_endpoint": "http://mockauth:8000/userinfo",
        "jwks_uri": "http://mockauth:8000/keyset",
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
        "id_token_signing_alg_values_supported": ["RS256", "RS384", "RS512", "HS256", "HS384", "HS512", "ES256"],
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
        "userinfo_signing_alg_values_supported": ["RS256", "RS384", "RS512", "HS256", "HS384", "HS512", "ES256"],
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


def init() -> web.Application:
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
