"""Mock OAUTH2 aiohttp.web server."""

from aiohttp import web
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend
from authlib.jose import jwt, jwk
from typing import Tuple
import urllib


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
jwk = generate_token()

header = {"jku": "http://mockauth:8000/jwk", "kid": "rsa1", "alg": "RS256", "typ": "JWT"}

user_info = {
    "sub": "smth",
    "eduPersonAffiliation": "member;staff",
    "eppn": "test@test.what",
    "displayName": "test test",
    "schacHomeOrganizationType": "urn:schac:homeOrganizationType:test:other",
    "given_name": "test",
    "uid": "test@test.what",
    "nsAccountLock": "false",
    "eduPersonScopedAffiliation": "staff@test.what;member@test.what",
    "name": "test test",
    "schacHomeOrganization": "test.what",
    "family_name": "test",
    "email": "test@test.what",
}


async def auth(req: web.Request) -> web.Response:
    """Auth endpoint."""
    params = {
        "state": req.query["state"],
        "code": "code",
    }
    global nonce
    nonce = req.query["nonce"]
    callback_url = req.query["redirect_uri"]
    url = f"{callback_url}?{urllib.parse.urlencode(params)}"
    response = web.HTTPSeeOther(url)
    return response


async def token(req: web.Request) -> web.Response:
    """Auth endpoint."""
    global nonce
    id_token = {
        "at_hash": "fSi3VUa5i2o2SgY5gPJZgg",
        "sub": "smth",
        "eduPersonAffiliation": "member;staff",
        "eppn": "test@test.what",
        "displayName": "test test",
        "iss": "http://mockauth:8000",
        "schacHomeOrganizationType": "urn:schac:homeOrganizationType:test:other",
        "given_name": "test",
        "nonce": nonce,
        "aud": "aud2",
        "acr": "http://mockauth:8000/LoginHaka",
        "nsAccountLock": "false",
        "eduPersonScopedAffiliation": "staff@test.what;member@test.what",
        "auth_time": 1606579533,
        "name": "test test",
        "schacHomeOrganization": "test.what",
        "exp": 9999999999,
        "iat": 1561621913,
        "family_name": "test",
        "email": "test@test.what",
    }
    data = {"access_token": "test", "id_token": jwt.encode(header, id_token, jwk[1]).decode("utf-8")}
    return web.json_response(data)


async def jwk_response(request: web.Request) -> web.Response:
    """Mock JSON Web Key server."""
    keys = [jwk[0]]
    keys[0]["kid"] = "rsa1"
    data = {"keys": keys}
    return web.json_response(data)


async def userinfo(request: web.Request) -> web.Response:
    """Mock an authentication to ELIXIR AAI for GA4GH claims."""
    return web.json_response(user_info)


def init() -> web.Application:
    """Start server."""
    app = web.Application()
    app.router.add_get("/authorize", auth)
    app.router.add_post("/token", token)
    app.router.add_get("/keyset", jwk_response)
    app.router.add_get("/userinfo", userinfo)
    return app


if __name__ == "__main__":
    web.run_app(init(), port=8000)
