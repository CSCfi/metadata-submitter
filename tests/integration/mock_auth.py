"""Mock OAUTH2 aiohttp.web server."""

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


nonce = ""
jwk_pair = generate_token()

user_eppn = ""
user_given_name = ""
user_family_name = ""

header = {"jku": "http://mockauth:8000/jwk", "kid": "rsa1", "alg": "RS256", "typ": "JWT"}


async def setmock(req: web.Request) -> web.Response:
    """Auth endpoint."""
    global user_eppn, user_family_name, user_given_name
    user_eppn = req.query["eppn"]
    user_family_name = req.query["family"]
    user_given_name = req.query["given"]

    logging.info(user_eppn, user_family_name, user_given_name)

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
    global nonce, user_eppn, user_family_name, user_given_name
    id_token = {
        "at_hash": "fSi3VUa5i2o2SgY5gPJZgg",
        "sub": "smth",
        "eduPersonAffiliation": "member;staff",
        "eppn": user_eppn,
        "displayName": f"{user_given_name} {user_family_name}",
        "iss": "http://mockauth:8000",
        "schacHomeOrganizationType": "urn:schac:homeOrganizationType:test:other",
        "given_name": user_given_name,
        "nonce": nonce,
        "aud": "aud2",
        "acr": "http://mockauth:8000/LoginHaka",
        "nsAccountLock": "false",
        "eduPersonScopedAffiliation": "staff@test.what;member@test.what",
        "auth_time": 1606579533,
        "name": f"{user_given_name} {user_family_name}",
        "schacHomeOrganization": "test.what",
        "exp": 9999999999,
        "iat": 1561621913,
        "family_name": user_family_name,
        "email": user_eppn,
    }
    data = {"access_token": "test", "id_token": jwt.encode(header, id_token, jwk_pair[1]).decode("utf-8")}

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
    global nonce, user_eppn, user_family_name, user_given_name
    user_info = {
        "sub": "smth",
        "eduPersonAffiliation": "member;staff",
        "eppn": user_eppn,
        "displayName": f"{user_given_name} {user_family_name}",
        "schacHomeOrganizationType": "urn:schac:homeOrganizationType:test:other",
        "given_name": user_given_name,
        "uid": user_eppn,
        "nsAccountLock": "false",
        "eduPersonScopedAffiliation": "staff@test.what;member@test.what",
        "name": f"{user_given_name} {user_family_name}",
        "schacHomeOrganization": "test.what",
        "family_name": user_family_name,
        "email": user_eppn,
    }

    logging.info(user_info)

    return web.json_response(user_info)


def init() -> web.Application:
    """Start server."""
    app = web.Application()
    app.router.add_get("/setmock", setmock)
    app.router.add_get("/authorize", auth)
    app.router.add_post("/token", token)
    app.router.add_get("/keyset", jwk_response)
    app.router.add_get("/userinfo", userinfo)
    return app


if __name__ == "__main__":
    web.run_app(init(), port=8000)
